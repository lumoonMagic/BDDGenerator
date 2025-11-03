# bdd_step_wizard.py
import streamlit as st
from parser_utils import (
    parse_feature_steps,
    parse_helper_file,
    infer_helper_and_method,
    generate_step_impl,
    build_full_module,
)

st.set_page_config(page_title="BDD Step Generator Wizard", layout="wide")
st.title("🧩 BDD Step File Generator Wizard")

feature_file = st.file_uploader("Upload Feature File (.feature)", type=["feature", "txt"])
helper_files = st.file_uploader(
    "Upload Helper Python Files (.py)", type=["py", "txt"], accept_multiple_files=True
)

if not feature_file or not helper_files:
    st.info("Please upload a feature file and at least one helper file.")
    st.stop()

# Parse files
feature_text = feature_file.read().decode("utf-8")
steps = parse_feature_steps(feature_text)

helpers = {}
for hf in helper_files:
    raw = hf.read().decode("utf-8")
    parsed = parse_helper_file(raw)
    for cname, cinfo in parsed["classes"].items():
        helpers[cname] = cinfo

context_vars = sorted(
    {p for s in steps if s["kind"] == "Given" for p in s["params"]}
)

st.sidebar.header("Imports & Setup")
imports = st.sidebar.text_area(
    "Imports", "from models.oracle_rubrik import Rubrik\nfrom models.oracle_connector import OracleConnection"
)
instantiations = st.sidebar.text_area(
    "Instantiations", "rubrik = Rubrik()\noracle = OracleConnection()"
)

st.subheader("Step Mapping Wizard")

if "mappings" not in st.session_state:
    st.session_state["mappings"] = {}

for i, step in enumerate(steps):
    st.markdown(f"### {i+1}. {step['kind']} — `{step['text']}`")
    key = f"map_{i}"
    with st.expander("Configure Step", expanded=False):
        inferred_helper, inferred_method = infer_helper_and_method(step["text"], helpers)
        step_type = st.radio(
            "Step Type", ["assign", "call", "skip"], key=key + "_type",
            index=0 if step["kind"] == "Given" else (1 if inferred_helper else 2)
        )

        mapping = {"type": step_type}
        if step_type == "assign":
            st.write("Will assign all step params to context variables automatically.")
        elif step_type == "call":
            helper_class = st.selectbox(
                "Select Helper Class", list(helpers.keys()),
                index=list(helpers.keys()).index(inferred_helper) if inferred_helper in helpers else 0,
                key=key + "_class"
            )
            instance_name = helper_class.lower()
            method_name = st.selectbox(
                "Select Method",
                list(helpers[helper_class]["methods"].keys()),
                index=list(helpers[helper_class]["methods"].keys()).index(inferred_method)
                if inferred_method in helpers[helper_class]["methods"]
                else 0,
                key=key + "_method"
            )
            st.caption(f"Signature: {method_name}({', '.join(helpers[helper_class]['methods'][method_name]['args'])})")

            param_map = {}
            for arg in helpers[helper_class]["methods"][method_name]["args"]:
                col1, col2 = st.columns([0.4, 0.6])
                with col1:
                    choice = st.selectbox(f"{arg} source", ["context", "literal"], key=f"{key}_{arg}_src")
                with col2:
                    if choice == "context":
                        sel = st.selectbox(f"Map {arg} to", ["--select--"] + context_vars, key=f"{key}_{arg}_ctx")
                        if sel == "--select--":
                            expr = st.text_input(f"Custom context var for {arg}", f"context.{arg}", key=f"{key}_{arg}_txt")
                        else:
                            expr = f"context.{sel}"
                    else:
                        expr = st.text_input(f"Literal value for {arg}", f'""', key=f"{key}_{arg}_lit")
                param_map[arg] = expr

            save_to = st.text_input("Save return value to context var (optional)", key=key + "_save")
            mapping.update(
                {
                    "class": helper_class,
                    "instance_name": instance_name,
                    "method": method_name,
                    "param_map": param_map,
                    "save_to": save_to or None,
                }
            )
        st.session_state["mappings"][key] = mapping

if st.button("Generate Step File"):
    imports_list = imports.splitlines()
    inst_list = instantiations.splitlines()
    impls = []
    for i, step in enumerate(steps):
        key = f"map_{i}"
        mapping = st.session_state["mappings"].get(key, {"type": "assign"})
        impls.append(generate_step_impl(step, mapping))
    code = build_full_module(imports_list, inst_list, impls)
    st.subheader("Generated Step File")
    st.code(code, language="python")
    st.download_button("Download Step File", data=code, file_name="generated_steps.py")
