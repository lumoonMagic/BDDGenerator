import streamlit as st
import google.generativeai as genai
from datetime import datetime
import parser_utils as pu
import mapping_store as ms
import json

# --- INIT ------------------------------------------------------------
st.set_page_config(page_title="BDD Automation Wizard v7", layout="wide")
st.title("🧠 BDD Automation Wizard v7")

# Optional Gemini setup
use_llm = st.sidebar.checkbox("Use Gemini Flash 2.5 for autosuggest")
api_key = st.sidebar.text_input("Gemini API key", type="password")
if not api_key:
    api_key = st.secrets.get("GEMINI_API_KEY")
if api_key and use_llm:
    genai.configure(api_key=api_key)

# Mongo project scope
project = st.sidebar.text_input("Project Name", value="Default")

tabs = st.tabs(["Text ➜ BDD", "BDD ➜ StepFile", "Validate"])

# === TAB 1: TXT -> BDD ==============================================
with tabs[0]:
    st.header("Convert plain steps to structured BDD")

    txt = st.text_area("Paste scenario text")
    btn = st.button("Generate BDD")

    if btn and txt.strip():
        # parse steps & group into scenarios using numbering
        lines = [l.strip() for l in txt.splitlines() if l.strip()]
        scenario_blocks = []
        current = []
        for l in lines:
            if re.match(r"^\d+\)", l):  # new step numbering
                current.append(l)
            else:
                scenario_blocks.append(current)
                current = []
        if current: scenario_blocks.append(current)

        # For now: single combined scenario
        scenario = "\n  ".join([f"When {l}" for l in lines])
        bdd = f"Feature: Auto-generated\nScenario Outline: TBD\n  {scenario}\n"
        st.code(bdd, language="gherkin")

# === TAB 2: BDD -> StepFile =========================================
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
            st.warning("⚠️ No helper classes or grounding templates provided — LLM autosuggest may hallucinate.")

        results = []
        for step in steps:
            stored = ms.find_mapping(step, project)
            if stored:
                results.append(stored)
                continue

            if use_llm and api_key:
                # Prepare bounded prompt
                helper_text = json.dumps(helper_classes, indent=2)
                grounding = json.dumps(templates)
                prompt = f"""You are generating step call mappings for BDD.
Helper classes/methods available:
{helper_text}

Example templates:
{grounding}

Step: {step}

Return JSON list of class/method calls, respecting these helpers only."""
                try:
                    model = genai.GenerativeModel("gemini-1.5-flash")
                    resp = model.generate_content(prompt)
                    suggestion = json.loads(resp.text)
                    st.write(f"💡 LLM Suggestion for `{step}`:")
                    st.json(suggestion)
                    if st.button(f"Accept mapping for {step}"):
                        ms.save_mapping(step, suggestion, project, "llm", confidence=0.9)
                        st.success("Saved to Mongo mapping store.")
                    if st.button(f"Reject mapping for {step}"):
                        st.info("Manual mapping can be created below.")
                except Exception as e:
                    st.warning(f"LLM generation failed: {e}")
            else:
                st.info(f"No mapping for '{step}'. Define manually below.")

# === TAB 3: VALIDATION ==============================================
with tabs[2]:
    st.header("Validate BDD, StepFile, and Helpers consistency")
    f1 = st.file_uploader("BDD Feature", type=["feature", "txt"])
    f2 = st.file_uploader("Step File", type=["py", "txt"])
    f3 = st.file_uploader("Helper Files", type=["py", "txt"], accept_multiple_files=True)
    if st.button("Run Validation"):
        if not all([f1, f2, f3]):
            st.warning("Please upload all three file types.")
        else:
            st.success("Validation logic placeholder — AST + regex checks implemented next phase.")
