"""Prompt templates (versioned, never hardcoded in logic).

Hard Rule #3: the substantive, swappable prompt text lives in `.md` files here, not
in Python. `load()` reads a template and injects variables with `string.Template`
(`$var` syntax) rather than `str.format` — because future prompts will contain literal
JSON braces `{ }`, and `.format` would choke on them. `safe_substitute` also tolerates
stray `$` in model-facing text instead of raising.
"""

from __future__ import annotations

from pathlib import Path
from string import Template

_DIR = Path(__file__).resolve().parent


def load(name: str, /, **variables: object) -> str:
    """Read `prompts/<name>.md` and substitute `$var` placeholders (if any)."""
    text = (_DIR / f"{name}.md").read_text(encoding="utf-8")
    if not variables:
        return text
    return Template(text).safe_substitute(**variables)
