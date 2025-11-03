"""
parser_utils.py

Parsing and code-generation utilities for the BDD Step Wizard.

Functions:
- parse_feature_text(feature_text)
- parse_helper_file(source_code)
- infer_helper_and_method(step_text, helpers)
- generate_step_impl(step, calls, default_instances)
- build_module(imports, instantiations, impls)
- extract_steps_with_inheritance(feature_text)
- collect_context_vars(steps, include_all=False)
- validate_stepfile_against_helpers(step_src, helpers)
- detect_ambiguous_steps(feature_steps)
"""

import ast
import re
from typing import List, Dict, Tuple, Any

STEP_PATTERN = re.compile(r'^(Scenario Outline:|Scenario:)?\s*(\[[^\]]+\])?\s*(.*)$')
STEP_LINE_PATTERN = re.compile(r'^\s*(Given|When|Then|And|But)\s+(.*)', re.IGNORECASE)
PARAM_PATTERN = re.compile(r'\{([^}]+)\}|<([^>]+)>|\"([^\"]+)\"|\'([^\']+)\'')


def extract_steps_with_inheritance(feature_text: str) -> List[Dict[str,Any]]:
    """
    Parse a feature text and return a list of steps, with And/But inheriting the last explicit type.
    Each step is a dict: {'kind': 'given'/'when'/'then', 'text':..., 'params':[...], 'raw': line}
    """
    steps = []
    last_kind = None
    for raw in feature_text.splitlines():
        m = STEP_LINE_PATTERN.match(raw)
        if not m:
            continue
        token, rest = m.group(1), m.group(2)
        token_cap = token.capitalize()
        if token_cap in ("And", "But"):
            if last_kind:
                kind = last_kind
            else:
                # default to given if nothing before
                kind = "given"
        else:
            kind = token_cap.lower()
            last_kind = kind
        # find params
        params = []
        for pm in PARAM_PATTERN.finditer(rest):
            for g in pm.groups():
                if g:
                    params.append(g.strip("<>"))
        steps.append({"kind": kind, "text": rest.strip(), "params": params, "raw": raw})
    return steps


def parse_feature_text(feature_text: str) -> Dict[str, Any]:
    """
    Returns parsed structure with steps and scenario outlines details (minimally)
    """
    lines = feature_text.splitlines()
    scenarios = []
    cur = None
    for line in lines:
        line_strip = line.strip()
        if line_strip.lower().startswith("scenario outline:") or line_strip.lower().startswith("scenario:"):
            # start new scenario
            if cur:
                scenarios.append(cur)
            cur = {"header": line_strip, "lines": []}
        elif cur:
            cur["lines"].append(line)
    if cur:
        scenarios.append(cur)
    # flatten steps via extract_steps_with_inheritance for the whole file
    steps = extract_steps_with_inheritance(feature_text)
    return {"scenarios": scenarios, "steps": steps}


def parse_helper_file(source_code: str) -> Dict[str, Dict[str, List[str]]]:
    """
    AST-parse a helper python file and return dictionary:
      { "ClassName": { "method_name": ["arg1","arg2"], ... }, ... }
    Only normal class methods and functions are inspected. Does not execute code.
    """
    result: Dict[str, Dict[str, List[str]]] = {}
    try:
        tree = ast.parse(source_code)
    except Exception:
        return result
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods = {}
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    args = [a.arg for a in item.args.args if a.arg != "self"]
                    methods[item.name] = args
            result[node.name] = methods
    return result


def infer_helper_and_method(step_text: str, helpers: Dict[str, Dict[str, List[str]]]) -> Tuple[str, str]:
    """
    Try to infer helper class and a likely method name from step_text.
    Returns (helper_class_name or None, method_name or None)
    Uses keyword heuristics and method-name token matching.
    """
    txt = step_text.lower()
    helper = None
    # domain heuristics
    if any(k in txt for k in ("backup", "snapshot", "sla", "restore", "export", "snapshot_id")):
        helper = next((h for h in helpers.keys() if "rubrik" in h.lower()), None) or (list(helpers.keys())[0] if helpers else None)
    elif any(k in txt for k in ("database", "pdb", "create", "drop", "table", "connect")):
        helper = next((h for h in helpers.keys() if "oracle" in h.lower() or "sql" in h.lower() or "mssql" in h.lower()), None) or (list(helpers.keys())[0] if helpers else None)
    else:
        helper = next(iter(helpers), None)

    method = None
    if helper and helper in helpers:
        candidate_methods = list(helpers[helper].keys())
        # exact token matching on method name
        for m in candidate_methods:
            tokens = [t for t in re.split(r'[_\s]+', m.lower()) if t]
            if any(tok in txt for tok in tokens):
                method = m
                break
        # fallback heuristics
        if not method:
            if "backup" in txt:
                if "oracle_backup" in candidate_methods:
                    method = "oracle_backup"
            if not method and "archive" in txt and "archive" in " ".join(candidate_methods):
                method = next((c for c in candidate_methods if "archive" in c.lower()), None)
    return helper, method


def generate_step_impl(step: Dict[str,Any], calls: List[Dict[str,Any]], default_instances: Dict[str,str]) -> str:
    """
    Generate a behave step implementation for a single feature step.
    - step: {'kind': 'given'/'when'/'then', 'text':..., 'params':[...]}
    - calls: list of calls; each call:
        {'class': 'Rubrik', 'instance': 'rubrik', 'method': 'oracle_backup',
         'param_map': {'database_id': 'context.database_name', 'sla_id': 'context.sla_id'},
         'save_to': 'backup_status' OR 'context.backup_status' or '' }
    - default_instances: mapping class->default_instance_name (e.g., {'Rubrik':'rubrik'})
    Output: a string with decorator + def + body
    """
    decorator = f"@{step['kind']}('{step['text']}')"
    func_args = ["context"] + step.get("params", [])
    func_sig = f"def step_impl({', '.join(func_args)}):"
    body_lines = []

    # If Given and no calls: auto-assign params to context
    if step['kind'] == 'given' and not calls:
        for p in step.get("params", []):
            body_lines.append(f"context.{p} = {p}")
    else:
        # For each call, pre-assign the parameters, then call and optionally save
        for c in calls:
            param_map: Dict[str,str] = c.get("param_map", {})
            # Pre-assign each param as a variable with the parameter name
            for pname, pexpr in param_map.items():
                # pexpr is expected to be a python expression like context.var or a literal or a saved var name
                body_lines.append(f"{pname} = {pexpr}")
            inst = c.get("instance") or default_instances.get(c.get("class"), c.get("class").lower())
            # call using the parameter variable names in order of insertion
            args_list = ", ".join(list(param_map.keys()))
            call_expr = f"{inst}.{c['method']}({args_list})" if args_list else f"{inst}.{c['method']}()"
            save_to = c.get("save_to")
            if save_to:
                # if save_to starts with "context.", leave as-is
                if save_to.startswith("context."):
                    body_lines.append(f"{save_to} = {call_expr}")
                else:
                    # default to local var; user can choose to store in context explicitly
                    body_lines.append(f"{save_to} = {call_expr}")
            else:
                body_lines.append(call_expr)
    if not body_lines:
        body_lines.append("pass")
    indented = "\n".join("    " + l for l in body_lines)
    return f"{decorator}\n{func_sig}\n{indented}\n"


def build_module(imports: List[str], instantiations: List[str], step_impls: List[str]) -> str:
    header = ["from behave import given, when, then"] + imports + [""]
    inst_block = instantiations + [""]
    body = step_impls
    return "\n".join(header + inst_block + body)


def collect_context_vars(steps: List[Dict[str,Any]], include_all: bool=False) -> List[str]:
    """
    Collect context variables from Given and their Ands, and optionally from all steps.
    Returns deduplicated list.
    """
    vars = []
    last = None
    for s in steps:
        kind = s['kind'].lower()
        if include_all:
            for p in s.get('params', []):
                vars.append(p)
        else:
            if kind == 'given':
                for p in s.get('params', []):
                    vars.append(p)
                last = 'given'
            elif kind in ('and', 'but') and last == 'given':
                for p in s.get('params', []):
                    vars.append(p)
            else:
                last = kind
    # deduplicate but preserve order
    seen = set()
    out = []
    for v in vars:
        if v not in seen:
            out.append(v)
            seen.add(v)
    return out


# -----------------------
# Validation helpers
# -----------------------
def validate_stepfile_against_helpers(step_src: str, helpers: Dict[str, Dict[str, List[str]]]) -> List[Dict[str, Any]]:
    """
    Parse a steps.py source and check for calls that do not match any helper class methods.
    Return list of issues like:
      {"type":"missing_method","instance":"rubrik","method":"oracle_backup"}
    """
    issues = []
    try:
        tree = ast.parse(step_src)
    except Exception as e:
        return [{"type":"syntax_error", "msg": str(e)}]
    # collect helper method names for lookup
    helper_map = {}
    for cls, methods in helpers.items():
        helper_map[cls] = set(methods.keys())
    # find Call nodes
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                # function invoked as instance.method()
                if isinstance(func.value, ast.Name):
                    inst = func.value.id  # instance var name
                    mname = func.attr
                    # naive mapping: match instance name to helper class by lower-case
                    matched_cls = None
                    for cls in helper_map:
                        if inst.lower() == cls.lower() or inst.lower() == cls.lower()[0:len(inst)]:
                            matched_cls = cls
                            break
                    if matched_cls:
                        if mname not in helper_map.get(matched_cls, set()):
                            issues.append({"type": "missing_method", "instance": inst, "mapped_class": matched_cls, "method": mname})
                    else:
                        # unknown instance - could be local var or not a helper
                        issues.append({"type":"unknown_instance", "instance": inst, "method": mname})
    return issues


def detect_ambiguous_steps(feature_steps: List[Dict[str,Any]]) -> List[Dict[str,Any]]:
    """
    Simple duplicate detection of identical step texts (case-insensitive).
    """
    seen = {}
    issues = []
    for s in feature_steps:
        key = s['text'].strip().lower()
        seen.setdefault(key, 0)
        seen[key] += 1
    for k, v in seen.items():
        if v > 1:
            issues.append({"type": "duplicate_step", "text": k, "count": v})
    return issues
