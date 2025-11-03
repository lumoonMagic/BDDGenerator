import re
import os
import streamlit as st

def parse_feature_file(content: str):
    """Extract individual BDD steps from a .feature file."""
    steps = []
    for line in content.splitlines():
        line = line.strip()
        if re.match(r"^(Given|When|Then|And|But)\b", line, re.IGNORECASE):
            kind = re.match(r"^(Given|When|Then|And|But)", line, re.IGNORECASE).group(1).lower()
            text = re.sub(r"^(Given|When|Then|And|But)\s*", "", line, flags=re.IGNORECASE)
            steps.append({"kind": kind, "text": text})
    return steps

def parse_helper_classes(content):
    """Extract classes and methods from a Python helper file."""
    classes = {}
    current = None
    for line in content.splitlines():
        c = re.match(r'^\s*class\s+(\w+)', line)
        if c:
            current = c.group(1)
            classes[current] = []
        f = re.match(r'^\s*def\s+(\w+)\(', line)
        if f and current:
            classes[current].append(f.group(1))
    return classes

def load_grounding_templates(template_dir="templates"):
    """Safely load any BDD/step/helper templates to ground LLM."""
    templates = {}
    if not os.path.exists(template_dir):
        st.warning(f"⚠️ Template folder '{template_dir}' not found.")
        return templates
    for fn in os.listdir(template_dir):
        try:
            with open(os.path.join(template_dir, fn), "r", encoding="utf-8") as f:
                templates[fn] = f.read()
        except Exception as e:
            st.warning(f"Failed reading template {fn}: {e}")
    return templates
