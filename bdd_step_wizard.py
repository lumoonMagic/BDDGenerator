import streamlit as st, re, json
import parser_utils as pu
import mapping_store as ms
import validator_utils as vu
from datetime import datetime
import google.generativeai as genai

st.set_page_config(page_title="BDD Automation Wizard v7.3", layout="wide")
st.title("🧠 BDD Automation Wizard v7.3")

# ---- Sidebar: Configuration ----
use_llm = st.sidebar.checkbox("Use Gemini 2.5 Flash for autosuggest", value=True)
api_key = st.sidebar.text_input("Gemini API key", type="password")
if not api_key:
    api_key = st.secrets.get("GEMINI_API_KEY")
if api_key and use_llm:
    genai.configure(api_key=api_key)

project = st.sidebar.text_input("Project Name", value="Default")

tabs = st.tabs(["Text ➜ BDD", "BDD ➜ StepFile", "Validate"])

# ======================================================================
# === TAB 1: TEXT -> BDD ===============================================
# ======================================================================
with tabs[0]:
    st.header("Convert plain steps to BDD")
    txt = st.text_area("Paste raw scenario steps")
    if st.button("Generate BDD"):
        lines = [l.strip() for l in txt.splitlines() if l.strip()]
        scenario = "\n  ".join([f"When {l}" for l in lines])
        bdd = f"Feature: Auto-generated\nScenario Outline: TBD\n  {scenario}\n"
        st.code(bdd, language="gherkin")

# ======================================================================
# === TAB 2: BDD -> STEPFILE ==========================================
# ======================================================================
with tabs[1]:
    st.header("Generate StepFile from BDD + Helpers")

    feat = st.file_uploader("Upload BDD feature file", type=["feature", "txt"])
    helpers = st.file_uploader("Upload helper python files", type=["py", "txt"], accept_multiple_files=True)
    grounding_files = st.file_uploader("Upload grounding templates (optional)", type=["txt", "feature", "py"], accept_multiple_files=True)

    simulate = st.button("Simulate Step Generation")

    if simulate and feat:
        feature_text = feat.read().decode("utf-8")
        steps = pu.parse_feature_file(feature_text)

        # Parse helpers
        helper_classes = {}
        for f in helpers or []:
            content = f.read().decode("utf-8")
            helper_classes.update(pu.parse_helper_classes(content))

        # Load grounding templates safely
        repo_templates = pu.load_grounding_templates()
        uploaded_grounding = {}
        for f in grounding_files or []:
            try:
                uploaded_grounding[f.name] = f.read().decode("utf-8")
            except Exception as e:
                st.warning(f"Failed reading {f.name}: {e}")
        templates = {**repo_templates, **uploaded_grounding}

        if not helper_classes and not templates:
            st.warning("⚠️ No helper classes or grounding templates provided — LLM may hallucinate.")

        # Iterate through each step
        for i, s in enumerate(steps):
            step = s["text"]
            st.markdown(f"### 🔹 Step {i+1}: {s['kind'].upper()} {step}")

            suggestion = None
            stored = None

            # 1️⃣ Try LLM autosuggest first
            if use_llm and api_key:
                helper_text = json.dumps(helper_classes, indent=2)
                grounding = json.dumps(templates)
                prompt = f"""
You are a BDD step mapping generator for test automation.
Only use the helper classes and methods shown below. 
Respond strictly in JSON format as a list of call objects.

Helper classes/methods:
{helper_text}

Grounding context (sample BDD and step templates):
{grounding}

Step: {step}

Return JSON list, e.g.:
[{{"class_name": "Rubrik", "method_name": "get_oracle_db_id", "save_to": "context.db_id"}}]
"""
                try:
                    model = genai.GenerativeModel("gemini-2.5-flash")
                    resp = model.generate_content(prompt)
                    text = (resp.text or "").strip()
                    if not text:
                        st.warning("⚠️ Gemini returned empty response.")
                        suggestion = []
                    else:
                        match = re.search(r"(\[.*\]|\{.*\})", text, re.S)
                        if match:
                            suggestion = json.loads(match.group(1))
                        else:
                            st.warning(f"⚠️ LLM output not JSON:\n{text[:400]}")
                            suggestion = []
                except Exception as e:
                    st.warning(f"LLM generation failed: {e}")
                    suggestion = []

            # 2️⃣ Fallback to stored mapping (Mongo)
            if not suggestion:
                stored = ms.find_mapping(step, project)
                if stored:
                    st.success("✅ Found mapping in MongoDB.")
                    st.json(stored)
                    continue

            # 3️⃣ Show suggestion if available
            if suggestion:
                st.write("💡 Gemini Suggested Mapping:")
                st.json(suggestion)
                if st.button(f"Accept mapping for '{step}'", key=f"accept_{i}"):
                    ms.save_mapping(step, suggestion, project, "llm", confidence=0.9)
                    st.success("Mapping saved to MongoDB.")
                if st.button(f"Reject mapping for '{step}'", key=f"reject_{i}"):
                    st.info("You can edit or create a manual mapping below.")
            else:
                st.info("No valid mapping found. Please define manually below.")

            # 4️⃣ Manual mapping UI (always visible fallback)
            st.write("🔧 Manual Mapping Builder:")
            selected_class = st.selectbox(
                "Helper Class", list(helper_classes.keys()) or ["<none>"], key=f"class_{i}"
            )
            if selected_class != "<none>":
                selected_method = st.selectbox(
                    "Method", helper_classes[selected_class], key=f"method_{i}"
                )
                param_input = st.text_area("Parameter mapping (JSON)", value='{}', key=f"param_{i}")
                save_var = st.text_input("Save return to (optional)", value="", key=f"save_{i}")
                if st.button(f"Save manual mapping for '{step}'", key=f"savebtn_{i}"):
                    try:
                        helper_chain = [{
                            "class_name": selected_class,
                            "method_name": selected_method,
                            "param_map": json.loads(param_input or "{}")
                        }]
                        if save_var:
                            helper_chain[0]["save_to"] = save_var
                        ms.save_mapping(step, helper_chain, project, "manual", confidence=1.0)
                        st.success("Manual mapping saved to MongoDB.")
                    except Exception as e:
                        st.error(f"Failed to save mapping: {e}")

# ======================================================================
# === TAB 3: VALIDATOR ================================================
# ======================================================================
with tabs[2]:
    st.header("Validate BDD ⇄ StepFile ⇄ Helpers")
    f1 = st.file_uploader("BDD Feature", type=["feature", "txt"])
    f2 = st.file_uploader("Step File", type=["py", "txt"])
    f3 = st.file_uploader("Helper Files", type=["py", "txt"], accept_multiple_files=True)

    if st.button("Run Validation"):
        if not all([f1, f2, f3]):
            st.warning("Please upload all three files.")
        else:
            feature = f1.read().decode("utf-8")
            step_py = f2.read().decode("utf-8")
            helpers = {}
            for hf in f3:
                helpers.update(vu.parse_helper_signatures(hf.read().decode("utf-8")))

            st.subheader("🧩 Decorator Validation")
            for line, note in vu.validate_decorators(step_py):
                st.write(f"`{line}` → {note}")

            st.subheader("🔍 Function Call Validation")
            val = vu.validate_stepfile(step_py, helpers)
            good = [v for v in val if v["valid"]]
            bad = [v for v in val if not v["valid"]]
            st.success(f"✅ Valid calls: {len(good)}")
            st.error(f"❌ Invalid calls: {len(bad)}")
            if bad:
                st.table(bad)

            st.subheader("📄 Inline Editor")
            edited = st.text_area("Edit Step File", value=step_py, height=300)
            if st.button("Re-validate after Edit"):
                val2 = vu.validate_stepfile(edited, helpers)
                st.info(f"Now valid {sum(v['valid'] for v in val2)} of {len(val2)}")
