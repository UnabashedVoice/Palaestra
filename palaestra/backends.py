"""
backends.py — Model backends for LLMAgent, borrowed from Actualizer.

Actualizer's LMStudioBackend already handles what local models need
(gpt-oss Harmony rendering and identity, chat templates for everything
else), so Palaestra reuses it rather than keeping a second copy. It looks
for Actualizer as a sibling folder, or at $PALAESTRA_ACTUALIZER.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_DEFAULT_ACTUALIZER = Path(__file__).resolve().parents[2] / "Actualizer"


def _import_actualizer_backend():
    root = Path(os.environ.get("PALAESTRA_ACTUALIZER", _DEFAULT_ACTUALIZER))
    if not (root / "actualizer" / "backend.py").exists():
        raise RuntimeError(
            f"Actualizer not found at {root}; set PALAESTRA_ACTUALIZER to its folder."
        )
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from actualizer import backend  # noqa: WPS433
    return backend


def load_backend(spec: str, timeout: int = 3600):
    """
    'lmstudio:<model identifier>' -> Actualizer's LMStudioBackend.
    For gpt-oss models it uses Actualizer's current local identity.
    """
    kind, _, model = spec.partition(":")
    if kind != "lmstudio" or not model:
        raise ValueError(f"unsupported agent spec {spec!r}; expected 'lmstudio:<model>'")
    backend = _import_actualizer_backend()
    # Actualizer versions before the local-identity work have no `identity` parameter;
    # fall back to their default rather than failing.
    identity = getattr(backend, "GPT_OSS_IDENTITY_VERSION", None)
    if "gpt-oss" in model.lower() and identity is not None:
        return backend.LMStudioBackend(model=model, timeout=timeout, identity=identity)
    return backend.LMStudioBackend(model=model, timeout=timeout)
