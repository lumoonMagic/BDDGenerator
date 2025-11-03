import ast, re, astor, streamlit as st

def parse_helper_signatures(helper_text):
    """Return {Class: [methods]}."""
    classes = {}
    current = None
    for line in helper_text.splitlines():
        c = re.match(r'^\s*class\s+(\w+)', line)
        if c:
            current = c.group(1)
            classes[current] = []
        f = re.match(r'^\s*def\s+(\w+)\((.*?)\)', line)
        if f and current:
            classes[current].append(f.group(1))
    return classes

def extract_function_calls(step_py):
    """Return list of (class.method, args) from stepfile."""
    calls = []
    try:
        tree = ast.parse(step_py)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute):
                    call = f"{getattr(func.value, 'id', 'unknown')}.{func.attr}"
                elif isinstance(func, ast.Name):
                    call = func.id
                else:
                    call = "unknown"
                args = [astor.to_source(a).strip() for a in node.args]
                calls.append((call, args))
    except SyntaxError as e:
        st.error(f"Syntax error parsing step file: {e}")
    return calls

def validate_stepfile(step_py, helpers_dict):
    """Compare step calls to helper signatures."""
    calls = extract_function_calls(step_py)
    results = []
    for call, args in calls:
        valid = False
        for cls, methods in helpers_dict.items():
            if "." in call:
                prefix, m = call.split(".", 1)
                if m in methods:
                    valid = True
                    break
        results.append({"call": call, "args": args, "valid": valid})
    return results

def validate_decorators(step_py):
    """Check that And/But inherit correct decorator type."""
    lines = step_py.splitlines()
    report = []
    last_type = None
    for l in lines:
        m = re.match(r'@(given|when|then|and|but)', l, re.I)
        if m:
            tag = m.group(1).lower()
            if tag in ["and", "but"]:
                if not last_type:
                    report.append((l, "⚠️ And/But with no previous type"))
                else:
                    report.append((l, f"Inherits → @{last_type}"))
            else:
                last_type = tag
    return report
