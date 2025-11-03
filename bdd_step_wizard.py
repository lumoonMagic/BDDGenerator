import streamlit as st, re, json
import parser_utils as pu
import mapping_store as ms
import validator_utils as vu
from datetime import datetime
import google.generativeai as genai

st.set_page_config(page_title="BDD Automation Wizard v7.1", layout="wide")
st.title("🧠 BDD Automation Wizard v7.1")

use_llm = st.sidebar.checkbox("Use Gemini Flash 2.5 for autosuggest")
api_key = st.sidebar.text_input("Gemini API key", type="password")
if not api_key:
    api_key = st.secrets.get("GEMINI_API_KEY")
if api_key and use_llm:
    genai.configure(api_key=api_key)
project = st.sidebar.text_input("Project Name", value="Default")

tabs = st.tabs(["Text ➜ BDD", "BDD ➜ StepFile", "Validate"])

# --- TEXT -> BDD -----------------------------------------------------
with tabs[0]:
    st.header("Convert plain steps to BDD")
    txt = st.text_area("Paste raw scenario steps")
    if st.button("Generate BDD"):
        lines = [l.strip() for l in txt.splitlines() if l.strip()]
        scenario = "\n  ".join([f"When {l}" for l in lines])
        bdd = f"Feature: Auto-generated\nScenario Outline: TBD\n  {scenario}\n"
        st.code(bdd, language="gherkin")

# --- BDD -> STEPFILE -------------------------------------------------
with tabs[1]:
    st.header("Generate StepFile from BDD + Helpers")
    feat = st.file_uploader("Upload BDD feature file", type=["feature", "txt"])
    helpers = st.file_uploader("Upload helper python files", type=["py", "txt"], accept_multiple_files=True)
    grounding_files = st.file_uploader("Upload grounding templates (optional)", type=["txt", "feature", "py"], accept_multiple_files=True)
    simulate = st.button("Simulate Step Generation")

    if simulate and feat:
        feature_text = feat.read().decode("utf-8")
        steps = pu.parse_feature_file(feature_text)
        helper_classes = {}
        for f in helpers or []:
            content = f.read().decode("utf-8")
            helper_classes.update(pu.parse_helper_classes(content))
        repo_templates = pu.load_grounding_templates()
        uploaded_grounding = {}
        for f in grounding_files or []:
            try:
                uploaded_grounding[f.name] = f.read().decode("utf-8")
            except Exception as e:
                st.warning(f"Failed reading {f.name}: {e}")
        templates = {**repo_templates, **uploaded_grounding}
        if not helper_classes and not templates:
            st.warning("⚠️ No helper classes or grounding templates — LLM may hallucinate.")

        for s in steps:
            step = s["text"]
            stored = ms.find_mapping(step, project)
            st.markdown(f"**Step:** {s['kind'].upper()} {step}")
            if stored:
                st.success("Found mapping in Mongo.")
                st.json(stored)
                continue
            if use_llm and api_key:
                helper_text = json.dumps(helper_classes, indent=2)
                grounding = json.dumps(templates)
                prompt = f"""You are generating step call mappings for BDD.
Helper classes/methods available:
{helper_text}
Grounding examples:
{grounding}
Step: {step}
Return JSON list of valid class/method calls ONLY from helpers."""
                try:
                    model = genai.GenerativeModel("gemini-2.5-flash")
                    resp = model.generate_content(prompt)
                    suggestion = json.loads(resp.text)
                    st.write("💡 LLM Suggestion:")
                    st.json(suggestion)
                    if st.button(f"Accept mapping for '{step}'"):
                        ms.save_mapping(step, suggestion, project, "llm", confidence=0.9)
                        st.success("Saved mapping.")
                    if st.button(f"Reject mapping for '{step}'"):
                        st.info("Manual mapping available below.")
                except Exception as e:
                    st.warning(f"LLM generation failed: {e}")
            else:
                st.info("No mapping found. Define manually.")

# --- VALIDATOR -------------------------------------------------------
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
