"""RFC 8785-compatible canonical bytes for contract identities.

The project contract domain intentionally forbids JSON floats.  That removes the
only implementation-defined part of ECMAScript number rendering while retaining
the RFC 8785 UTF-16 object-key ordering required by the reviewed vectors.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence


class CanonicalizationError(ValueError):
    """Raised when a value cannot be represented by the frozen JSON profile."""


def canonical_json(value: object) -> str:
    """Return deterministic RFC 8785 JSON for the no-float contract profile."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        raise CanonicalizationError("JSON floats are forbidden in canonical contract values")
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise CanonicalizationError("canonical object keys must be strings")
        keys = sorted(value, key=lambda key: key.encode("utf-16-be", "surrogatepass"))
        return (
            "{"
            + ",".join(f"{canonical_json(key)}:{canonical_json(value[key])}" for key in keys)
            + "}"
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return "[" + ",".join(canonical_json(item) for item in value) + "]"
    raise CanonicalizationError(f"unsupported canonical value: {type(value).__name__}")


def canonical_bytes(value: object) -> bytes:
    """Return UTF-8 canonical bytes without BOM."""
    return canonical_json(value).encode("utf-8")


def canonical_sha256(value: object) -> str:
    """Return lowercase SHA-256 of the canonical bytes."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()
