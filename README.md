# BDD Step Wizard v5.3

This repository contains the **BDD Step Wizard** — a Streamlit application to:
- Parse Gherkin `.feature` files and helper `.py` files
- Auto-simulate and generate Behave step implementation files
- Transform plain English test flow into strict Scenario Outline BDD files (templates)
- Validate generated stepfiles against helpers and features
- Optionally use Gemini Flash 2.5 (Google generative AI) to assist mapping and disambiguation

## Files

- `bdd_step_wizard.py` — main Streamlit app (entrypoint)
- `parser_utils.py` — parsing, AST inspection, and code-generation utilities
- `requirements.txt` — dependencies

## Requirements

Add to `requirements.txt`:
