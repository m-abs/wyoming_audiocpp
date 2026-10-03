"""Load audio.cpp model param types for wire-body coercion.

Types come from audio.cpp's webui ``model_params.json`` (keyed by model id,
each entry a list of {name, type, ...}). The reference copy under
``references/`` is freshest in the devcontainer; the bundled copy is the
reliable fallback for Docker where ``references/`` is absent.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

_REPO_ROOT = Path(__file__).resolve().parent.parent
_REFERENCE = _REPO_ROOT / "references/audio.cpp/webui/configs/model_params.json"
_BUNDLED = Path(__file__).resolve().parent / "params.json"


def _load() -> Dict[str, list]:
    for path in (_REFERENCE, _BUNDLED):
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return {}


def param_types(model: str) -> Dict[str, str]:
    """Return {param_name: type} for a model; empty when the model is unknown."""
    entries = _load().get(model, [])
    return {e["name"]: e["type"] for e in entries if "name" in e and "type" in e}


def coerce(model: str, name: str, value: Any) -> Any:
    """Coerce a param value to its declared type; pass through when unknown."""
    t = param_types(model).get(name)
    if t in ("number", "slider"):
        return float(value)
    if t == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        return str(value).strip().lower() in ("true", "1", "yes")
    if t in ("text", "choice"):
        return str(value)
    return value  # unknown type: trust the config.json value as-is
