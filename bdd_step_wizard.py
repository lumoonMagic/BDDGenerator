# bdd_step_wizard.py
import streamlit as st
import json
import textwrap
import os
from typing import List, Dict, Any
import parser_utils as pu

st.set_page_config(page_title="BDD Step Wizard v5.5", layout="wide")
st.title("BDD Step Wizard v5.5 — with mapping store & autosuggest")

# Sidebar settings and secrets
with st.sidebar:
    st.header("Settings")
    default_import = st.text_input("Default import line", "from myhelpers import Rubrik, OracleConnection")
    default_inst = st.text_input("Default instantiation lines (one per line)", "rubrik = Rubrik()\noracle = OracleConnection()")
    st.checkbox("Include parameters from ALL steps in context dropdowns", key="include_all_context", value=False)
    st.markdown("---")
    st.header("LLM (optional)")
    llm_enable = st.checkbox("Enable Gemini Flash 2.5", value=False)
    gemini_key = None
    if llm_enable:
        gemini_key = st.text_input("Gemini API Key (optional, falls back to st.secrets if blank)", type="password")
        if not gemini_key and "GEMINI_API_KEY" in st.secrets:
            gemini_key = st.secrets["GEMINI_API_KEY"]

# mapping store load
mappings_store = pu.load_mappings_store()

# Helper: save store and sync session
def persist_store():
    pu.save_mappings_store(mappings_store)
    st.experimental_rerun()

# Tabs
tab_wizard, tab_simulate, tab_transform, tab_validator = st.tabs(["Wizard", "Simulate", "Transform (Text→BDD)", "Validator"])

# --------------------
# Wizard tab
# --------------------
with tab_wizard:
    st.header("Wizard — Map BDD Steps to Helper Methods (interactive)")
    st.write("Upload a .feature and helper files, then map each step. Use saved mappings to auto-suggest.")
    feat = st.file_uploader("Feature file (.feature)", type=["feature","txt"], key="wiz_feat")
    helpers = st.file_uploader("Helper files (.py/.txt)", accept_multiple_files=True, type=["py","txt"], key="wiz_helpers")

    if feat and helpers:
        feature_text = feat.read().decode("utf-8", errors="ignore")
        parsed = pu.parse_feature_text(feature_text)
        steps = parsed["steps"]
        # parse helpers
        helper_map = {}
        for hf in helpers:
            content = hf.read().decode("utf-8", errors="ignore")
            helper_map.update(pu.parse_helper_file(content))

        st.subheader("Parsed steps")
        for i, s in enumerate(steps):
            st.markdown(f"**{i+1}.** [{s['kind'].upper()}] {s['text']} — params: {s['params']}")

        # session mapping store
        if "wizard_mappings" not in st.session_state:
            st.session_state["wizard_mappings"] = {}

        # helper defaults
        default_instances = {cls: cls.lower() for cls in helper_map.keys()}

        # autosuggest based on stored mappings
        for idx, step in enumerate(steps):
            key = f"step_{idx}"
            with st.expander(f"Configure step {idx+1}: {step['text']}", expanded=False):
                # try suggesting mapping
                suggestion = pu.suggest_mapping_for_step(step['text'], mappings_store)
                if suggestion:
                    st.info("Saved mapping suggestion found — you can accept or edit it.")
                    if key not in st.session_state['wizard_mappings']:
                        st.session_state['wizard_mappings'][key] = suggestion
                # show mapping area
                mapping = st.session_state['wizard_mappings'].get(key, {"calls": []})
                mode = st.selectbox(f"Mode_{key}", options=["auto-assign (Given)", "call-chain", "skip"], index=0 if step['kind']=='given' else 1)
                if mode.startswith("auto") or step['kind']=='given':
                    st.write("This will assign step parameters into context.")
                    mapping = {"calls": []}
                    # create trivial mapping in memory
                    for p in step.get("params", []):
                        mapping.setdefault("assigns", []).append({"param": p, "target": f"context.{p}"})
                else:
                    calls = mapping.get("calls", [])
                    for ci, call in enumerate(calls):
                        st.markdown(f"### Call {ci+1}")
                        col1, col2 = st.columns([0.45, 0.55])
                        with col1:
                            cls_opts = list(helper_map.keys()) or [""]
                            cls_choice = st.selectbox(f"{key}_cls_{ci}", options=cls_opts, index=cls_opts.index(call.get("class")) if call.get("class") in cls_opts else 0)
                        with col2:
                            inst_name = st.text_input(f"{key}_inst_{ci}", value=call.get("instance") or cls_choice.lower())
                        methods = list(helper_map.get(cls_choice, {}).keys()) if cls_choice else []
                        method_choice = st.selectbox(f"{key}_method_{ci}", options=methods, index=(methods.index(call.get("method")) if call.get("method") in methods else 0) if methods else 0)
                        # parameters
                        param_map = call.get("param_map", {})
                        new_map = {}
                        for arg in helper_map.get(cls_choice, {}).get(method_choice, []):
                            choice_type = st.selectbox(f"{key}_{ci}_{arg}_type", ["context","literal","saved"], index=0)
                            if choice_type == "context":
                                # show discovered context vars
                                ctxts = pu.collect_context_vars(steps, include_all=st.session_state.get("include_all_context", False))
                                ctxts = ["--select--"] + ctxts + [c for c in calls if c.get("save_to")]
                                sel = st.selectbox(f"{key}_{ci}_{arg}_ctx", options=ctxts, key=f"{key}_{ci}_{arg}_ctx")
                                if sel == "--select--":
                                    expr = st.text_input(f"{key}_{ci}_{arg}_ctx_txt", value=f"context.{arg}", key=f"{key}_{ci}_{arg}_ctx_txt")
                                else:
                                    if sel.startswith("context."):
                                        expr = sel
                                    else:
                                        expr = f"context.{sel}" if not sel.startswith("context.") else sel
                            elif choice_type == "literal":
                                expr = st.text_input(f"{key}_{ci}_{arg}_lit", value='""', key=f"{key}_{ci}_{arg}_lit")
                            else:
                                # saved variable
                                saved_opts = [c.get("save_to") for c in calls if c.get("save_to")]
                                saved_opts = ["--select--"] + [s for s in saved_opts if s]
                                if saved_opts and len(saved_opts) > 1:
                                    sel = st.selectbox(f"{key}_{ci}_{arg}_saved", options=saved_opts, key=f"{key}_{ci}_{arg}_saved")
                                    expr = sel if sel != "--select--" else st.text_input(f"{key}_{ci}_{arg}_saved_txt", value=arg)
                                else:
                                    expr = st.text_input(f"{key}_{ci}_{arg}_saved_txt2", value=arg)
                            new_map[arg] = expr
                        save_to = st.text_input(f"{key}_{ci}_save", value=call.get("save_to",""), help="Enter 'context.varname' or 'varname' to persist the result into context")
                        # update call object
                        call.update({"class": cls_choice, "instance": inst_name, "method": method_choice, "param_map": new_map, "save_to": save_to})
                        calls[ci] = call
                        mapping["calls"] = calls
                        st.session_state['wizard_mappings'][key] = mapping
                    if st.button(f"Add call to step {idx+1}", key=f"addcall_{idx}"):
                        inferred_cls, inferred_method = pu.infer_helper_and_method(step['text'], helper_map)
                        mapping.setdefault("calls", []).append({"class": inferred_cls or (list(helper_map.keys())[0] if helper_map else ""), "instance": (inferred_cls.lower() if inferred_cls else ""), "method": inferred_method, "param_map": {}, "save_to": ""})
                        st.session_state['wizard_mappings'][key] = mapping

                # Save mapping button to persist this step mapping
                if st.button(f"Save mapping for step {idx+1}", key=f"save_map_{idx}"):
                    # store mapping (as-is) into mappings_store under normalized key
                    mapping_to_save = st.session_state['wizard_mappings'].get(key, {})
                    pu.save_mapping_for_step(step['text'], mapping_to_save)
                    st.success("Mapping saved to store (mappings_store.json).")

        # Generate consolidated stepfile
        if st.button("Generate Stepfile from mappings"):
            imports = [default_import]
            insts = default_inst.splitlines()
            impls = []
            known_context_vars = set()
            for i, s in enumerate(steps):
                key = f"step_{i}"
                mapping = st.session_state['wizard_mappings'].get(key, {"calls":[]})
                impls.append(pu.generate_step_impl(s, mapping.get("calls", []), default_instances, known_context_vars))
            module_text = pu.build_module(imports, insts, impls)
            st.subheader("Generated Stepfile")
            st.code(module_text, language="python")
            st.download_button("Download generated_steps.py", module_text, file_name="generated_steps.py")

# --------------------
# Simulate tab
# --------------------
with tab_simulate:
    st.header("Simulate — auto-suggest mappings for a feature")
    st.write("Upload a feature and helper files, then run Simulation. Saved mappings will be suggested automatically when steps match.")
    feat = st.file_uploader("Feature file (for simulation)", type=["feature","txt"], key="sim_feat")
    helpers = st.file_uploader("Helper files", accept_multiple_files=True, type=["py","txt"], key="sim_helpers")
    use_llm_sim = st.checkbox("Use Gemini for simulation?", key="sim_llm")
    gemini_key_sim = None
    if use_llm_sim:
        gemini_key_sim = st.text_input("Gemini API Key (optional)", type="password", key="sim_gem_key")
        if not gemini_key_sim and "GEMINI_API_KEY" in st.secrets:
            gemini_key_sim = st.secrets["GEMINI_API_KEY"]

    if st.button("Run simulation"):
        if not feat or not helpers:
            st.warning("Please upload a feature and helper files.")
        else:
            ftxt = feat.read().decode("utf-8")
            steps = pu.extract_steps_with_inheritance(ftxt)
            helper_map = {}
            for hf in helpers:
                helper_map.update(pu.parse_helper_file(hf.read().decode("utf-8")))
            suggestions = {}
            for i, stp in enumerate(steps):
                # first check saved mapping
                suggestion = pu.suggest_mapping_for_step(stp['text'], mappings_store)
                if suggestion:
                    suggestions[i] = suggestion
                    continue
                # heuristic infer
                h, m = pu.infer_helper_and_method(stp['text'], helper_map)
                calls = []
                if stp['kind'] == 'given':
                    suggestions[i] = {"calls": []}
                    continue
                if h and m:
                    arglist = helper_map.get(h, {}).get(m, [])
                    pmap = {}
                    for a in arglist:
                        if a in stp.get('params', []):
                            pmap[a] = f"context.{a}"
                        elif "db" in a and any("database" in p for p in stp.get('params', [])):
                            pmap[a] = "context.database_name"
                        elif "table" in a and any("table" in p for p in stp.get('params', [])):
                            pmap[a] = "context.table_name"
                        else:
                            pmap[a] = '""'
                    calls.append({"class": h, "instance": h.lower(), "method": m, "param_map": pmap, "save_to": ""})
                suggestions[i] = {"calls": calls}
            # if LLM requested, optionally call gemini to refine (not implemented full parsing for brevity)
            # load suggestions into wizard mappings
            st.session_state['wizard_mappings'] = {}
            for i, s in enumerate(steps):
                st.session_state['wizard_mappings'][f"step_{i}"] = suggestions.get(i, {"calls":[]})
            st.success("Suggestions loaded into Wizard tab for editing.")

# --------------------
# Transform tab (Text -> BDD)
# --------------------
with tab_transform:
    st.header("Transform: Free text -> BDD (multi-scenario)")
    text_in = st.text_area("Paste free-text flow (or upload)", height=300)
    up = st.file_uploader("Or upload text file", type=["txt","md"])
    if up and not text_in:
        text_in = up.read().decode("utf-8")
    use_llm_t = st.checkbox("Use Gemini to refine BDD?", key="llm_transform")
    gem_key_t = None
    if use_llm_t:
        gem_key_t = st.text_input("Gemini API Key (optional)", type="password", key="gem_t")
        if not gem_key_t and "GEMINI_API_KEY" in st.secrets:
            gem_key_t = st.secrets["GEMINI_API_KEY"]
    templates = pu.load_grounding_templates()
    grounding_text = "\n\n".join([f"### {n}\n{c}" for n,c in templates.items()])

    if st.button("Generate BDD from text"):
        if not text_in or not text_in.strip():
            st.error("Provide text input")
        else:
            bdd = pu.generate_bdd_from_text(text_in, use_llm=use_llm_t, api_key=gem_key_t, grounding_text=grounding_text)
            st.code(bdd, language="gherkin")
            st.download_button("Download generated .feature", bdd, file_name="generated_from_text.feature")

# --------------------
# Validator tab
# --------------------
with tab_validator:
    st.header("Validate BDD + Step File + Helpers")
    f = st.file_uploader("Feature file", type=["feature","txt"], key="val_feat")
    sfile = st.file_uploader("Step implementation file (.py)", type=["py"], key="val_step")
    hf = st.file_uploader("Helper files (.py/.txt)", accept_multiple_files=True, type=["py","txt"], key="val_helpers")

    if st.button("Run validation"):
        if not (f and sfile and hf):
            st.error("Please upload all required files.")
        else:
            ftxt = f.read().decode("utf-8")
            stxt = sfile.read().decode("utf-8")
            helper_map = {}
            for h in hf:
                helper_map.update(pu.parse_helper_file(h.read().decode("utf-8")))
            parsed = pu.parse_feature_text(ftxt)
            feature_steps = parsed["steps"]
            amb = pu.detect_ambiguous_steps(feature_steps)
            issues = pu.validate_stepfile_against_helpers(stxt, helper_map)
            # missing implementations: naive check
            missing = []
            for sstep in feature_steps:
                if sstep['text'] not in stxt:
                    missing.append(sstep['text'])
            report = {
                "duplicate_steps": amb,
                "missing_steps_by_text": missing,
                "issues_with_helpers": issues
            }
            st.json(report)

# --------------------
# Mapping store export/import UI
# --------------------
st.sidebar.markdown("---")
st.sidebar.header("Mappings store")
if st.sidebar.button("Download mappings store"):
    data = pu.load_mappings_store()
    st.sidebar.download_button("Download JSON", json.dumps(data, indent=2), file_name="mappings_store.json")
uploaded_store = st.sidebar.file_uploader("Upload mappings store JSON to replace current", type=["json"])
if uploaded_store:
    try:
        uploaded = json.load(uploaded_store)
        pu.save_mappings_store(uploaded)
        st.sidebar.success("Mappings store updated from uploaded file (restart may be needed).")
    except Exception as e:
        st.sidebar.error(f"Could not load uploaded JSON: {e}")

st.info("Mapping persistence stores user-saved mappings to mappings_store.json in app folder. On Streamlit Cloud, this persists during app runtime and can be exported/imported.")

# end of bdd_step_wizard.py
