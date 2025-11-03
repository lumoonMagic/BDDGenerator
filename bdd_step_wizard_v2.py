# bdd_step_wizard.py
import streamlit as st
from io import StringIO
import textwrap
import ast
import json
from typing import List, Dict, Any
import parser_utils as pu

# optional LLM
try:
    import google.generativeai as genai
except Exception:
    genai = None

st.set_page_config(page_title="BDD Step Wizard v5.3", layout="wide")
st.title("BDD Step Wizard v5.3 — Generic BDD / Stepfile Generator & Validator")

st.markdown("""
**Tabs**
- Wizard — interactive mapping: .feature + helper files -> generate step implementation(s) with multi-call chaining and pre-assignment.
- Simulate — auto-generate a first-pass stepfile using heuristics; optional Gemini Flash 2.5 assist.
- Transform (Text → BDD) — paste free-text test-flow and generate Scenario Outline(s) using your template.
- Validator — upload Feature + Step file + Helpers and validate mappings, syntax, and helper method usage.
""")

# Sidebar settings
with st.sidebar:
    st.header("Settings")
    st.text_input("Default helper import (for generated files, e.g. from models.oracle_rubrik import Rubrik)", key="default_import", value="from models.oracle_rubrik import Rubrik")
    st.text_input("Default instantiation (e.g. rubrik = Rubrik())", key="default_inst", value="rubrik = Rubrik()")
    st.checkbox("Include parameters from ALL steps in context dropdowns", key="include_all_context_vars", value=False)
    st.markdown("---")
    st.header("LLM (optional)")
    llm_enable = st.checkbox("Enable Gemini Flash 2.5 for Simulate", value=False)
    if llm_enable:
        # read from secrets if available else prompt
        gemini_key = st.text_input("Gemini API Key (or leave blank to use st.secrets['GEMINI_API_KEY'])", type="password")
        if not gemini_key and "GEMINI_API_KEY" in st.secrets:
            gemini_key = st.secrets["GEMINI_API_KEY"]
        st.session_state["gemini_key"] = gemini_key

tabs = st.tabs(["Wizard", "Simulate", "Transform (Text→BDD)", "Validator", "About"])
tab_wizard, tab_simulate, tab_transform, tab_validator, tab_about = tabs

# Helper: safe call to Gemini
def call_gemini(prompt: str, api_key: str):
    if not genai:
        st.warning("google-generativeai library not installed; install it in requirements to use Gemini.")
        return None
    if not api_key:
        st.error("No Gemini API key provided.")
        return None
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        resp = model.generate_content(prompt)
        return resp.text
    except Exception as e:
        st.error(f"Gemini call failed: {e}")
        return None

# --------------------
# Wizard Tab
# --------------------
with tab_wizard:
    st.header("Wizard — Interactive Mapping & Stepfile Generation")
    st.markdown("Upload feature and helper files, then map steps to helper methods. Supports multi-call chaining.")
    feature_file = st.file_uploader("Upload Feature (.feature)", type=["feature","txt"], key="wiz_feat")
    helper_files = st.file_uploader("Upload Helper Python files (.py or .txt) — multiple allowed", accept_multiple_files=True, type=["py","txt"], key="wiz_helpers")

    if feature_file and helper_files:
        feature_text = feature_file.read().decode("utf-8", errors="ignore")
        parsed = pu.parse_feature_text(feature_text)
        steps = parsed["steps"]
        helpers_parsed = {}
        for hf in helper_files:
            txt = hf.read().decode("utf-8", errors="ignore")
            parsed_h = pu.parse_helper_file(txt)
            # flatten into helpers_parsed mapping class->methods
            for cls, methods in parsed_h.items():
                helpers_parsed[cls] = methods

        st.subheader("Parsed steps (with And/But inheritance applied)")
        for i,s in enumerate(steps):
            st.write(f"{i+1}. [{s['kind'].upper()}] {s['text']} — params: {s['params']}")

        context_vars = pu.collect_context_vars(steps, include_all=st.session_state.get("include_all_context_vars", False))
        st.write("Context variables discovered (from Given + And under Given):", context_vars)

        # Setup session storage
        if 'wizard_mappings' not in st.session_state:
            st.session_state['wizard_mappings'] = {}

        default_imports = [st.session_state["default_import"]]
        default_insts = [st.session_state["default_inst"]]

        for idx, step in enumerate(steps):
            key = f"step_{idx}"
            with st.expander(f"Step {idx+1} — [{step['kind'].upper()}] {step['text']}", expanded=False):
                # default mapping type
                mapping = st.session_state['wizard_mappings'].get(key, {"calls": []})
                map_type = st.selectbox("Implementation mode", options=["auto-assign", "call-chain", "skip"], key=key+"_type", index=0 if step['kind']=='given' else 1)
                if map_type == "auto-assign" or step['kind']=='given':
                    st.info("This will assign step params to context variables.")
                    # store mapping
                    mapping = {"calls": []}
                elif map_type == "skip":
                    mapping = {"calls": []}
                else:
                    # call-chain mode
                    # show existing calls
                    calls = mapping.get("calls", [])
                    for ci, call in enumerate(calls):
                        st.markdown(f"Call {ci+1}")
                        col1, col2 = st.columns([0.45, 0.55])
                        with col1:
                            cls_choice = st.selectbox(f"{key}_cls_{ci}", options=list(helpers_parsed.keys()), index=(list(helpers_parsed.keys()).index(call.get("class")) if call.get("class") in helpers_parsed else 0))
                        with col2:
                            inst_name = st.text_input(f"{key}_inst_{ci}", value=call.get("instance") or cls_choice.lower())
                        methods = list(helpers_parsed[cls_choice].keys())
                        method_choice = st.selectbox(f"{key}_method_{ci}", options=methods, index=(methods.index(call.get("method")) if call.get("method") in methods else 0))
                        # Param mapping UI
                        param_map = call.get("param_map", {})
                        new_map = {}
                        for arg in helpers_parsed[cls_choice][method_choice]:
                            colA, colB = st.columns([0.4,0.6])
                            with colA:
                                src = st.radio(f"{key}_{ci}_{arg}_src", options=["context", "literal", "saved"], index=0 if param_map.get(arg, "").startswith("context.") else (1 if param_map.get(arg, "").startswith(("'",'"')) else (2 if param_map.get(arg,"") else 0)))
                            with colB:
                                if src == "context":
                                    # build context dropdown (include saved vars)
                                    saved = [c.get("save_to") for c in calls if c.get("save_to")]
                                    options = ["--select--"] + list(dict.fromkeys(context_vars + [s for s in saved if s]))
                                    sel = st.selectbox(f"{key}_{ci}_{arg}_ctx", options=options, key=f"{key}_{ci}_{arg}_ctx_key")
                                    if sel == "--select--":
                                        expr = st.text_input(f"{key}_{ci}_{arg}_ctx_txt", value=f"context.{arg}", key=f"{key}_{ci}_{arg}_ctx_txt")
                                    else:
                                        # if user chose a saved var (no 'context.'), keep as-is; else map to context.var
                                        if sel.startswith("context."):
                                            expr = sel
                                        elif sel in (saved or []):
                                            expr = sel  # local saved var
                                        else:
                                            expr = f"context.{sel}"
                                elif src == "literal":
                                    expr = st.text_input(f"{key}_{ci}_{arg}_lit", value='""', key=f"{key}_{ci}_{arg}_lit")
                                else:
                                    # saved var selection
                                    saved = [c.get("save_to") for c in calls if c.get("save_to")]
                                    saved = [s for s in saved if s]
                                    if saved:
                                        choice = st.selectbox(f"{key}_{ci}_{arg}_saved", options=["--select--"] + saved, key=f"{key}_{ci}_{arg}_saved_key")
                                        expr = choice if choice != "--select--" else st.text_input(f"{key}_{ci}_{arg}_saved_txt", value=arg)
                                    else:
                                        expr = st.text_input(f"{key}_{ci}_{arg}_saved_none", value=arg)
                            new_map[arg] = expr
                        save_to = st.text_input(f"{key}_{ci}_save", value=call.get("save_to",""))
                        # update call
                        call.update({"class": cls_choice, "instance": inst_name, "method": method_choice, "param_map": new_map, "save_to": save_to})
                        mapping["calls"] = calls
                        st.session_state['wizard_mappings'][key] = mapping
                    # Add new call button
                    if st.button(f"Add call to step {idx+1}", key=f"addcall_{idx}"):
                        inferred_cls, inferred_method = pu.infer_helper_and_method(step['text'], helpers_parsed)
                        mapping.setdefault("calls", []).append({"class": inferred_cls or (list(helpers_parsed.keys())[0] if helpers_parsed else ""), "instance": (inferred_cls.lower() if inferred_cls else ""), "method": inferred_method, "param_map": {}, "save_to": ""})
                        st.session_state['wizard_mappings'][key] = mapping

                st.session_state['wizard_mappings'][key] = mapping

        # Generate stepfile
        if st.button("Generate Stepfile from Wizard mappings"):
            imports = [st.session_state["default_import"]]
            insts = [st.session_state["default_inst"]]
            impls = []
            for i, s in enumerate(steps):
                key = f"step_{i}"
                mapping = st.session_state['wizard_mappings'].get(key, {"calls":[]})
                impls.append(pu.generate_step_impl(s, mapping.get("calls", []), {cls: cls.lower() for cls in helpers_parsed.keys()}))
            module_text = pu.build_module(imports, insts, impls)
            st.subheader("Generated Stepfile")
            st.code(module_text, language="python")
            st.download_button("Download Stepfile", module_text, file_name="generated_steps.py")

# --------------------
# Simulate Tab
# --------------------
with tab_simulate:
    st.header("Simulate — Auto generate first-pass stepfile")
    st.markdown("This runs heuristics to map steps to helper methods. Optionally use Gemini (LLM) to improve suggestions. Unresolved mappings are shown and user can edit them in Wizard tab.")
    feat = st.file_uploader("Feature (.feature) to simulate", type=["feature","txt"], key="sim_feat")
    helpers = st.file_uploader("Helper files (.py/.txt)", accept_multiple_files=True, type=["py","txt"], key="sim_helpers")
    use_llm_sim = st.checkbox("Use Gemini Flash 2.5 to assist simulation?", key="sim_use_llm")
    if use_llm_sim:
        gemini_key_sim = st.text_input("Gemini API Key (or use st.secrets['GEMINI_API_KEY'])", type="password", key="sim_key")
        if not gemini_key_sim and "GEMINI_API_KEY" in st.secrets:
            gemini_key_sim = st.secrets["GEMINI_API_KEY"]

    if st.button("Run Simulation"):
        if not feat or not helpers:
            st.error("Please upload a feature file and at least one helper file.")
        else:
            feature_text = feat.read().decode("utf-8", errors="ignore")
            parsed = pu.parse_feature_text(feature_text)
            steps = parsed["steps"]
            helper_map = {}
            for hf in helpers:
                text = hf.read().decode("utf-8", errors="ignore")
                helper_map.update(pu.parse_helper_file(text))
            suggestions = {}
            # basic heuristics
            for i, s in enumerate(steps):
                if s['kind'] == 'given':
                    suggestions[i] = {"calls": []}
                    continue
                h, m = pu.infer_helper_and_method(s['text'], helper_map)
                calls = []
                if h and m:
                    # build naive param_map by matching names
                    arglist = helper_map.get(h, {}).get(m, [])
                    pmap = {}
                    for a in arglist:
                        # prefer context var with same name, else try db/table mapping, else blank literal
                        if a in s.get('params', []):
                            pmap[a] = f"context.{a}"
                        elif 'db' in a and any('database' in p for p in s.get('params', [])):
                            pmap[a] = "context.database_name"
                        elif 'table' in a and any('table' in p for p in s.get('params', [])):
                            pmap[a] = "context.table_name"
                        else:
                            pmap[a] = '""'
                    calls.append({"class": h, "instance": h.lower(), "method": m, "param_map": pmap, "save_to": ""})
                suggestions[i] = {"calls": calls}
            # optional LLM assist: craft a compact JSON prompt and call Gemini synchronously
            if use_llm_sim and gemini_key_sim:
                # build grounding: feature text + helper list
                helper_summaries = []
                for cls, methods in helper_map.items():
                    for mname, args in methods.items():
                        helper_summaries.append(f"{cls}.{mname}({', '.join(args)})")
                prompt = f"""
You are an assistant that maps feature steps to helper class methods.
Feature steps:
{feature_text}

Helpers:
{chr(10).join(helper_summaries)}

Return JSON array of objects with fields:
[{{"step":"<exact step text>", "calls":[{{"class":"Rubrik","method":"oracle_backup","param_map":{{}},"save_to":""}}]}}]
If uncertain about param_map, leave empty.
"""
                llm_out = call_gemini(prompt, gemini_key_sim)
                if llm_out:
                    try:
                        parsed_json = json.loads(llm_out)
                        # merge suggestions into our suggestions structure
                        for item in parsed_json:
                            # find matching step index by step text
                            for i, s in enumerate(steps):
                                if s['text'].strip() == item.get('step','').strip():
                                    suggestions[i] = {"calls": item.get("calls", [])}
                    except Exception:
                        st.warning("Could not parse Gemini response as JSON; keeping heuristic suggestions.")
            # load suggestions into session mappings for editing in Wizard
            st.success("Simulation complete — suggestions loaded into Wizard tab for review.")
            st.session_state['wizard_mappings'] = {}
            for i, s in enumerate(steps):
                key = f"step_{i}"
                st.session_state['wizard_mappings'][key] = suggestions.get(i, {"calls":[]})

# --------------------
# Transform (Text -> BDD)
# --------------------
with tab_transform:
    st.header("Transform: Free-text -> BDD generator (Scenario Outline templates)")
    st.markdown("Paste your plain-language test flow and choose a template. The generator will produce Scenario Outline(s) that strictly follow your template syntax.")
    text_in = st.text_area("Paste test-flow text (or upload below)", height=220)
    upload_text = st.file_uploader("Or upload plain text file (.txt)", type=["txt","md"])
    if upload_text:
        text_in = upload_text.read().decode("utf-8", errors="ignore")
    template_choice = st.selectbox("Template style", options=["MSSQL Restore (Scenario Outline)", "Generic Flow (simple Scenario)"])
    require_confirm = st.checkbox("Require user confirmation for missing params (prompt before generation)", value=True)
    if st.button("Generate BDD from text"):
        if not text_in.strip():
            st.error("Provide text describing the flow.")
        else:
            # Simple parser: split numbered steps and prerequisites
            lines = [l.strip() for l in text_in.splitlines() if l.strip()]
            prereq = []
            steps_list = []
            for l in lines:
                if l.lower().startswith("prerequisite") or l.lower().startswith("prereq"):
                    prereq.append(l)
                elif l[0].isdigit() or l.lower().startswith(("step", "when", "then", "given")):
                    steps_list.append(l)
                else:
                    # try to classify into prereq if early lines
                    if not steps_list:
                        prereq.append(l)
                    else:
                        steps_list.append(l)
            # extract placeholder tokens from text e.g., <db_name> or words like server_ip
            placeholders = set()
            for l in lines:
                for pm in pu.PARAM_PATTERN.finditer(l):
                    for g in pm.groups():
                        if g:
                            placeholders.add(g.strip("<>"))
            # If template is MSSQL Restore, render strict template
            if template_choice.startswith("MSSQL"):
                # try to extract placeholders for example table
                # if missing critical params, ask user (if require_confirm)
                needed = ["server_ip","platform","os","snapshot_id","database_name","table_name","mssql_version","table_delete_status","check_table_status","trigger_restore_status","restore_status","db_exists_status","table_exists","table_data_status"]
                missing = [n for n in needed if n not in placeholders]
                if missing and require_confirm:
                    st.warning("The input text doesn't contain all required placeholders. Please provide the missing parameter names or uncheck the confirmation requirement.")
                    st.write("Missing placeholders:", missing)
                    add_manual = st.text_input("Add missing placeholders (comma separated) to include in Examples header", value=",".join(missing))
                    if st.button("Confirm and continue"):
                        for x in [p.strip() for p in add_manual.split(",") if p.strip()]:
                            placeholders.add(x)
                    else:
                        st.stop()
                # build the strict scenario
                ex_headers = " | ".join(needed)
                ex_row = "| 10.81.91.111 | IAAS (AWS) | Windows 2022 | valid | SDLC_78_2022  | test_table_2022 | 2022 | Table deleted successfully | Table test_table_2022 does not exist | Restore triggered | Restore successful | Database SDLC_78_2022 exists | Table test_table_2022 exists | Table data matched |"
                bdd = textwrap.dedent(f"""
                Scenario Outline: [2] Perform Successful MSSQL Restore on Same Server
                  Given TDE enabled database <database_name> with <table_name> was backed up successfully on <server_ip>
                  And the snapshot id is <snapshot_id>
                  When the table <table_name> is dropped from <database_name>
                  Then the method confirms table deletion status <table_delete_status>
                  When the method to get the <table_name> is called
                  Then the method returns <check_table_status> status <table_name>
                  When the method to trigger full database restore on <server_ip> is called
                  Then the restore trigger status is <trigger_restore_status>
                  When the method to check restore job status is called
                  Then the restore completion status is <restore_status>
                  When the restored table <table_name> is queried
                  And the table existence status is <table_exists>
                  And the table data verification status is <table_data_status>
                  Examples:
                    | server_ip    | platform   | os           | snapshot_id | database_name | table_name      | mssql_version | table_delete_status         | check_table_status                    | trigger_restore_status | restore_status     | db_exists_status             | table_exists                 | table_data_status  |
                    {ex_row}
                """).strip()
                st.code(bdd, language="gherkin")
                st.download_button("Download generated .feature", bdd, file_name="generated_restore_scenario.feature")
            else:
                # Generic simple scenario generation
                # Map numbered steps to When/Then heuristically
                when_then = []
                for s in steps_list:
                    sl = s.lower()
                    if any(k in sl for k in ("create", "insert", "trigger", "drop", "prepare", "export")):
                        when_then.append(("when", s))
                    elif any(k in sl for k in ("check", "verify", "then", "returns", "status")):
                        when_then.append(("then", s))
                    else:
                        when_then.append(("when", s))
                # Build a single Scenario Outline
                b = ["Scenario Outline: Generated scenario"]
                for kt, txt in when_then:
                    b.append(f"  {kt.capitalize()} {txt}")
                # Build a simple Examples header from placeholders
                if placeholders:
                    hdr = " | ".join(sorted(placeholders))
                    ex_row = " | ".join(["VALUE"]*len(placeholders))
                    b.append("")
                    b.append("  Examples:")
                    b.append(f"    | {hdr} |")
                    b.append(f"    | {ex_row} |")
                out = "\n".join(b)
                st.code(out, language="gherkin")
                st.download_button("Download generated .feature", out, file_name="generated_generic.feature")

# --------------------
# Validator Tab
# --------------------
with tab_validator:
    st.header("Validator — Feature + Stepfile + Helper Validation")
    st.markdown("Upload a feature, a step implementation file, and the helper files. The validator will check: decorator inheritance, duplicate steps, syntax errors in stepfile, and calls to methods that don't exist on helper classes.")
    val_feat = st.file_uploader("Feature file (.feature)", type=["feature","txt"], key="val_feat")
    val_step = st.file_uploader("Step implementation file (.py)", type=["py"], key="val_step")
    val_helpers = st.file_uploader("Helper files (.py/.txt)", accept_multiple_files=True, type=["py","txt"], key="val_helpers")

    if st.button("Run Validation"):
        if not (val_feat and val_step and val_helpers):
            st.error("Please upload feature, stepfile, and helper file(s).")
        else:
            feat_txt = val_feat.read().decode("utf-8", errors="ignore")
            step_txt = val_step.read().decode("utf-8", errors="ignore")
            helpers_map = {}
            for hf in val_helpers:
                t = hf.read().decode("utf-8", errors="ignore")
                parsed = pu.parse_helper_file(t)
                for cls, methods in parsed.items():
                    helpers_map[cls] = methods
            # parse feature steps and find duplicates
            parsed = pu.parse_feature_text(feat_txt)
            feature_steps = parsed["steps"]
            amb = pu.detect_ambiguous_steps(feature_steps)
            issues = pu.validate_stepfile_against_helpers(step_txt, helpers_map)
            # check missing step implementations
            implemented_funcs = []
            try:
                tree = ast.parse(step_txt)
                for node in tree.body:
                    if isinstance(node, ast.FunctionDef):
                        implemented_funcs.append(node.name)
            except Exception as e:
                st.error(f"Error parsing stepfile: {e}")
            # map feature steps to decorators simplified (search for step text presence)
            missing_impl = []
            for s in feature_steps:
                found = False
                for node in ast.walk(ast.parse(step_txt)):
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ('given','when','then'):
                        pass
                # simpler: check if step text appears in stepfile source (safe heuristic)
                if s['text'] not in step_txt:
                    missing_impl.append(s['text'])
            st.subheader("Validation Report")
            if not amb and not issues and not missing_impl:
                st.success("No issues found — stepfile looks consistent with helpers and feature.")
            else:
                if amb:
                    st.warning("Ambiguous/duplicate steps found in feature:")
                    for a in amb:
                        st.write(a)
                if issues:
                    st.error("Issues found in stepfile usage of helper methods:")
                    for it in issues:
                        st.write(it)
                if missing_impl:
                    st.warning("Potential missing step implementations (step text not found in stepfile):")
                    for m in missing_impl:
                        st.write(m)
            # allow inline edit & re-validate
            st.subheader("Editable Stepfile (edit and re-run validation)")
            edited = st.text_area("Edit stepfile here", value=step_txt, height=400)
            if st.button("Re-run validation on edited stepfile"):
                issues2 = pu.validate_stepfile_against_helpers(edited, helpers_map)
                if not issues2:
                    st.success("Edited stepfile passed validation.")
                else:
                    st.error("Edited stepfile still has issues:")
                    for it in issues2:
                        st.write(it)

# --------------------
# About Tab
# --------------------
with tab_about:
    st.header("About BDD Step Wizard v5.3")
    st.markdown("""
    Features:
    - Generic wizard to map BDD steps to helper class methods (multi-call chaining, pre-assignment).
    - Simulate auto-generation with heuristics; optional Gemini Flash 2.5 LLM assist (synchronous).
    - Transform free-text test flows into Scenario Outline BDD templates that follow your syntax.
    - Validator to check feature vs stepfile vs helper implementations.
    - All LLM use is optional. If enabled, provide Gemini API key via UI or set `st.secrets['GEMINI_API_KEY']`.
    """)
    st.markdown("**Important:** LLM calls are synchronous and must be provided with a valid API key. Streamlit Cloud secrets are recommended for production.")
