"""
parser_utils.py

Parsing, generation, validation utilities and mapping-store helpers
for the BDD Step Wizard.

Functions exported:
- extract_steps_with_inheritance(feature_text)
- parse_feature_text(feature_text)
- parse_helper_file(source_code)
- infer_helper_and_method(step_text, helpers)
- generate_step_impl(step, calls, default_instances, known_context_vars)
- build_module(imports, instantiations, step_impls)
- collect_context_vars(steps, include_all=False)
- validate_stepfile_against_helpers(step_src, helpers)
- detect_ambiguous_steps(feature_steps)
- mapping store helpers: load_mappings_store(), save_mappings_store(), suggest_mapping_for_step()
- text->bdd generator: generate_bdd_from_text(...)
"""

import ast
import re
import json
import os
from typing import List, Dict, Any, Tuple

STEP_LINE_PATTERN = re.compile(r'^\s*(Given|When|Then|And|But)\s+(.*)', re.IGNORECASE)
PARAM_PATTERN = re.compile(r'\{([^}]+)\}|<([^>]+)\>|\"([^\"]+)\"|\'([^\']+)\'')

MAPPINGS_STORE_FILE = "mappings_store.json"


# -------------------------
# Feature parsing utilities
# -------------------------
def extract_steps_with_inheritance(feature_text: str) -> List[Dict[str, Any]]:
    """
    Return list of steps with 'kind' normalized to 'given'/'when'/'then'
    And/But inherit the previous explicit type.
    Each step: {'kind': 'given'/'when'/'then', 'text': '...', 'params': [...], 'raw': raw_line}
    """
    steps = []
    last_kind = None
    for raw in feature_text.splitlines():
        m = STEP_LINE_PATTERN.match(raw)
        if not m:
            continue
        token, rest = m.group(1), m.group(2).strip()
        token_lower = token.lower()
        if token_lower in ("and", "but"):
            if last_kind:
                kind = last_kind
            else:
                kind = "given"  # fallback
        else:
            kind = token_lower
            last_kind = kind
        params = []
        for pm in PARAM_PATTERN.finditer(rest):
            for g in pm.groups():
                if g:
                    params.append(g.strip("<>"))
        steps.append({"kind": kind, "text": rest, "params": params, "raw": raw})
    return steps


def parse_feature_text(feature_text: str) -> Dict[str, Any]:
    """
    Returns:
      {
        'scenarios': [ {'header': header_line, 'lines': [...]}, ... ],
        'steps': [ ... ]  # flattened with inheritance
      }
    """
    lines = feature_text.splitlines()
    scenarios = []
    cur = None
    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith("scenario outline:") or stripped.lower().startswith("scenario:"):
            if cur:
                scenarios.append(cur)
            cur = {"header": stripped, "lines": []}
        elif cur is not None:
            cur["lines"].append(line)
    if cur:
        scenarios.append(cur)
    steps = extract_steps_with_inheritance(feature_text)
    return {"scenarios": scenarios, "steps": steps}


# -------------------------
# Helper parsing utilities
# -------------------------
def parse_helper_file(source_code: str) -> Dict[str, Dict[str, List[str]]]:
    """
    AST parse helper python file.
    Return mapping: {ClassName: {method_name: [arg1,arg2,...], ...}, ...}
    """
    try:
        tree = ast.parse(source_code)
    except Exception:
        return {}
    out = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods = {}
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    args = [a.arg for a in item.args.args if a.arg != "self"]
                    methods[item.name] = args
            out[node.name] = methods
    return out


# -------------------------
# Mapping store (persistence)
# -------------------------
def load_mappings_store(filepath: str = MAPPINGS_STORE_FILE) -> Dict[str, Any]:
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_mappings_store(store: Dict[str, Any], filepath: str = MAPPINGS_STORE_FILE) -> bool:
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2)
        return True
    except Exception:
        return False


def make_step_key(step_text: str) -> str:
    """
    Normalize step text to key form: lowercase, strip variable placeholders
    e.g. "Trigger backup for <db_name>" -> "trigger backup for <param>"
    We'll replace angle-bracket contents with "<param>" token.
    """
    k = re.sub(r'<[^>]+>', '<param>', step_text)
    k = re.sub(r'\s+', ' ', k).strip().lower()
    return k


def suggest_mapping_for_step(step_text: str, store: Dict[str, Any]) -> Any:
    """
    Suggest saved mapping for a step:
    - Exact normalized key match
    - Fallback: best "prefix" match (naive)
    """
    k = make_step_key(step_text)
    if k in store.get("mappings", {}):
        return store["mappings"][k]
    # fuzzy: find any store entry where all words in short form match
    for key, mapping in store.get("mappings", {}).items():
        if key in k or k in key:
            return mapping
    return None


def save_mapping_for_step(step_text: str, mapping_obj: Dict[str, Any], store_filepath: str = MAPPINGS_STORE_FILE) -> bool:
    """
    Save mapping linked to normalized step key.
    mapping_obj contains the structure for 'calls' and other metadata.
    """
    store = load_mappings_store(store_filepath)
    if "mappings" not in store:
        store["mappings"] = {}
    store["mappings"][make_step_key(step_text)] = mapping_obj
    return save_mappings_store(store, store_filepath)


# -------------------------
# Heuristics
# -------------------------
def infer_helper_and_method(step_text: str, helpers: Dict[str, Dict[str, List[str]]]) -> Tuple[str, str]:
    txt = step_text.lower()
    helper = None
    # domain heuristics
    if any(k in txt for k in ("backup", "snapshot", "sla", "restore", "export")):
        helper = next((h for h in helpers.keys() if "rubrik" in h.lower()), None) or (list(helpers.keys())[0] if helpers else None)
    elif any(k in txt for k in ("database", "table", "create", "drop", "insert")):
        helper = next((h for h in helpers.keys() if any(x in h.lower() for x in ("oracle", "sql", "mssql"))), None) or (list(helpers.keys())[0] if helpers else None)
    else:
        helper = next(iter(helpers), None)
    method = None
    if helper and helper in helpers:
        candidate_methods = list(helpers[helper].keys())
        for m in candidate_methods:
            tokens = [t for t in re.split(r'[_\s]+', m.lower()) if t]
            # prefer method with tokens matching words in step
            if any(tok in txt for tok in tokens):
                method = m
                break
        if not method:
            # fallback to common method patterns
            for m in candidate_methods:
                if "backup" in m.lower() and "backup" in txt:
                    method = m
                    break
            if not method:
                method = candidate_methods[0] if candidate_methods else None
    return helper, method


# -------------------------
# Code generation
# -------------------------
def generate_step_impl(step: Dict[str, Any],
                       calls: List[Dict[str, Any]],
                       default_instances: Dict[str, str],
                       known_context_vars: set) -> str:
    """
    Create behave step implementation string for one step.
    - When calls include a 'save_to' value:
        if it starts with 'context.' -> assign return directly to that context member
        if it's a bare name -> assign to context.<name> (we will prefer context storage)
    - known_context_vars: set of names already in context; used to avoid re-fetching
    - For parameter mapping, expressions are used as provided (e.g., "context.db_id", '"literal"', "saved_var")
    """
    decorator = f"@{step['kind']}('{step['text']}')"
    func_args = ["context"] + step.get("params", [])
    func_sig = f"def step_impl({', '.join(func_args)}):"
    body_lines = []

    # If Given and no calls -> assign params into context
    if step['kind'] == 'given' and not calls:
        for p in step.get("params", []):
            body_lines.append(f"context.{p} = {p}")
            known_context_vars.add(p)
    else:
        # iterate through calls
        for c in calls:
            # if this call was marked as "use_cached" and its desired save_to already in known_context_vars, skip invocation
            # But we still might want to call if user explicitly forces it (not implemented here).
            save_to = c.get("save_to", "").strip()
            # Resolve target context var name
            if save_to:
                if save_to.startswith("context."):
                    ctx_name = save_to.split(".", 1)[1]
                    ctx_target = f"context.{ctx_name}"
                else:
                    # store in context by default to persist across steps
                    ctx_name = save_to
                    ctx_target = f"context.{ctx_name}"
            else:
                ctx_name = None
                ctx_target = None

            # if ctx_target already present in known_context_vars and the call is flagged as fetcher, skip calling again
            # We assume a call that returns a DB id is a fetcher if its method name contains 'get' or 'id' or 'fetch'
            method = c.get("method")
            is_fetcher = False
            if method and any(tok in method.lower() for tok in ("get", "id", "fetch")):
                is_fetcher = True
            if ctx_name and ctx_name in known_context_vars and is_fetcher:
                # skip invocation and just reuse existing context var
                # (user can choose to force re-fetch by providing a different save_to)
                continue

            # Pre-assign parameter expressions as local variables named after parameter names
            param_map = c.get("param_map", {}) or {}
            for pname, expr in param_map.items():
                # If expression is like 'context.xyz' or literal or saved var, use as provided
                body_lines.append(f"{pname} = {expr}")

            # Build instance name
            inst = c.get("instance") or default_instances.get(c.get("class"), (c.get("class") or "").lower())
            args_list = ", ".join(list(param_map.keys()))
            call_expr = f"{inst}.{method}({args_list})" if args_list else f"{inst}.{method}()"

            # If we need to save result, put into context.<name>
            if ctx_target:
                body_lines.append(f"{ctx_target} = {call_expr}")
                known_context_vars.add(ctx_name)
            else:
                body_lines.append(call_expr)

    if not body_lines:
        body_lines.append("pass")
    indented = "\n".join("    " + l for l in body_lines)
    return f"{decorator}\n{func_sig}\n{indented}\n"


def build_module(imports: List[str], instantiations: List[str], impls: List[str]) -> str:
    header = ["from behave import given, when, then"] + imports + [""]
    insts = instantiations + [""]
    return "\n".join(header + insts + impls)


def collect_context_vars(steps: List[Dict[str, Any]], include_all: bool = False) -> List[str]:
    last = None
    vars = []
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
    # dedupe preserving order
    seen = set()
    out = []
    for v in vars:
        if v not in seen:
            out.append(v)
            seen.add(v)
    return out


# -------------------------
# Validation helpers
# -------------------------
def validate_stepfile_against_helpers(step_src: str, helpers: Dict[str, Dict[str, List[str]]]) -> List[Dict[str, Any]]:
    issues = []
    try:
        tree = ast.parse(step_src)
    except Exception as e:
        return [{"type": "syntax_error", "msg": str(e)}]
    helper_map = {cls: set(methods.keys()) for cls, methods in helpers.items()}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                if isinstance(func.value, ast.Name):
                    inst = func.value.id
                    mname = func.attr
                    matched_cls = None
                    for cls in helper_map:
                        if inst.lower() == cls.lower() or inst.lower() == cls.lower()[0:len(inst)]:
                            matched_cls = cls
                            break
                    if matched_cls:
                        if mname not in helper_map.get(matched_cls, set()):
                            issues.append({"type": "missing_method", "instance": inst, "mapped_class": matched_cls, "method": mname})
                    else:
                        issues.append({"type": "unknown_instance", "instance": inst, "method": mname})
    return issues


def detect_ambiguous_steps(feature_steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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


# -------------------------
# Text -> BDD multi-scenario generator (improved)
# -------------------------
def generate_bdd_from_text(input_text: str, use_llm: bool = False, api_key: str = None, grounding_text: str = "") -> str:
    """
    Split input_text into logical scenario blocks and produce Scenario Outlines for each.
    If use_llm=True and api_key provided, call Gemini with grounding context to produce refined output.
    """
    # Split by numbered steps or blank line Section boundaries
    parts = re.split(r'\n\s*\d+\)|\n\s*Step\s+\d+|(?m)^\s*Scenario\s+\d+:', input_text)
    parts = [p.strip() for p in parts if p.strip()]
    scenarios = []
    # fallback: if no numbered parts, split by double newline
    if not parts:
        parts = [p.strip() for p in input_text.split("\n\n") if p.strip()]

    for idx, part in enumerate(parts, start=1):
        if use_llm and api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel("gemini-1.5-flash")
                prompt = f"""
You are a BDD generation assistant. Use the grounding examples and the description below to produce a Gherkin Scenario Outline that strictly follows the user's template style.

Grounding examples:
{grounding_text}

Description:
{part}

Return ONLY the Scenario Outline in Gherkin.
"""
                resp = model.generate_content(prompt)
                text = resp.text
                scenarios.append(text.strip())
                continue
            except Exception as e:
                scenarios.append(f"# Gemini failed: {e}\nScenario Outline: [{idx}] {part[:40]} ...")
        # Deterministic fallback: create a skeleton scenario outline
        scenarios.append(f"Scenario Outline: [{idx}] Auto generated scenario\n  # Source text:\n  {part.replace(chr(10), chr(10)+'  ')}")
    return "\n\n".join(scenarios)


# End of parser_utils.py
