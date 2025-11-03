# parser_utils.py
import ast
import re
from typing import List, Dict
import textwrap

STEP_PATTERN = re.compile(r'^(Given|When|Then|And|But)\s+(.*)', re.IGNORECASE)
PARAM_PATTERN = re.compile(r'\{([^}]+)\}|<([^>]+)>|\"([^\"]+)\"|\'([^\']+)\'')

def parse_feature_steps(feature_text: str) -> List[Dict]:
    steps = []
    for line in feature_text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = STEP_PATTERN.match(line)
        if not m:
            continue
        kind, text = m.groups()
        params = []
        for pm in PARAM_PATTERN.finditer(text):
            for g in pm.groups():
                if g:
                    params.append(g.strip("<>"))
        steps.append({"kind": kind.capitalize(), "text": text, "params": params})
    return steps


def parse_helper_file(source_code: str) -> Dict:
    tree = ast.parse(source_code)
    out = {"classes": {}}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods = {}
            for fn in node.body:
                if isinstance(fn, ast.FunctionDef):
                    args = [a.arg for a in fn.args.args if a.arg != "self"]
                    methods[fn.name] = {"args": args}
            out["classes"][node.name] = {"methods": methods}
    return out


def infer_helper_and_method(step_text: str, helpers: Dict) -> (str, str):
    text = step_text.lower()
    helper = None
    if "backup" in text or "restore" in text or "rubrik" in text:
        helper = "Rubrik"
    elif "oracle" in text or "database" in text or "pdb" in text:
        helper = "OracleConnection"
    if not helper:
        return None, None
    methods = list(helpers.get(helper, {}).get("methods", {}).keys())
    match = next((m for m in methods if any(k in text for k in m.lower().split("_"))), None)
    if not match and "backup" in text:
        match = "oracle_backup"
    elif not match and "restore" in text:
        match = "oracle_restore"
    return helper, match


def generate_step_impl(step, mapping):
    decorator = f"@{step['kind'].lower()}('{step['text']}')"
    args = ", ".join(["context"] + step["params"])
    body = []
    if mapping["type"] == "assign":
        for p in step["params"]:
            body.append(f"context.{p} = {p}")
    elif mapping["type"] == "call":
        pre = mapping.get("pre_assign", [])
        for line in pre:
            body.append(line)
        arglist = ", ".join(f"{k}={v}" for k, v in mapping["param_map"].items())
        call_line = f"{mapping['instance_name']}.{mapping['method']}({arglist})"
        if mapping.get("save_to"):
            call_line = f"context.{mapping['save_to']} = {call_line}"
        body.append(call_line)
    else:
        body.append("pass")
    body = "\n".join("    " + l for l in body)
    return f"{decorator}\ndef step_impl({args}):\n{body}\n"


def build_full_module(imports, instantiations, step_impls):
    header = ["from behave import given, when, then\n"]
    header += imports
    header = "\n".join(header) + "\n"
    init_block = "\n".join(instantiations) + "\n\n"
    steps_block = "\n\n".join(step_impls)
    return header + init_block + steps_block
