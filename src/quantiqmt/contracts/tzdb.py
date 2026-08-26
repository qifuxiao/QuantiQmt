"""Verified immutable IANA timezone database resource."""

from __future__ import annotations

import hashlib
import importlib.resources
import json
from io import BytesIO
from types import MappingProxyType
from zoneinfo import ZoneInfo

from quantiqmt.contracts.canonical import canonical_sha256

EXPECTED_TZDB_VERSION = "2026c"
EXPECTED_MANIFEST_CHECKSUM = "e815e8693332668600f0193bb43f5ed5a0d5e65d29967bbbf56d2765588f4e51"
EXPECTED_ZONES = frozenset({"Asia/Shanghai", "Asia/Tokyo", "America/New_York", "UTC"})


class TzdbIntegrityError(ValueError):
    """The deployed timezone artifact is absent, unknown, partial, or tampered."""


class FrozenTzdb:
    """Timezone resolver that never consults the host's system tzdb."""

    def __init__(self, manifest: bytes, files: dict[str, bytes]) -> None:
        try:
            document = json.loads(manifest.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TzdbIntegrityError("tzdb manifest is malformed") from exc
        if not isinstance(document, dict):
            raise TzdbIntegrityError("tzdb manifest root must be an object")
        version = document.get("iana_version")
        source = document.get("source")
        declared = document.get("files")
        checksum = document.get("manifest_checksum")
        if version != EXPECTED_TZDB_VERSION:
            raise TzdbIntegrityError("tzdb version mismatch")
        if not isinstance(source, str) or not source or not isinstance(declared, dict):
            raise TzdbIntegrityError("tzdb manifest is partial")
        if set(declared) != EXPECTED_ZONES or set(files) != EXPECTED_ZONES:
            raise TzdbIntegrityError("tzdb exact zone manifest mismatch")
        projection = {"iana_version": version, "source": source, "files": declared}
        if checksum != EXPECTED_MANIFEST_CHECKSUM or canonical_sha256(projection) != checksum:
            raise TzdbIntegrityError("tzdb manifest checksum mismatch")
        for name, expected in declared.items():
            if not isinstance(expected, str) or hashlib.sha256(files[name]).hexdigest() != expected:
                raise TzdbIntegrityError(f"tzdb zone digest mismatch: {name}")
        self._version: str = version
        self._files = MappingProxyType(dict(files))
        self._cache: dict[str, ZoneInfo] = {}
        digest_lines = [f"{name}:{declared[name]}" for name in sorted(declared)]
        self._bundle_digest = hashlib.sha256(
            (f"{version}\n{checksum}\n" + "\n".join(digest_lines)).encode("ascii")
        ).hexdigest()

    @classmethod
    def installed(cls) -> FrozenTzdb:
        try:
            root = importlib.resources.files("quantiqmt.contracts.resources").joinpath("tzdb")
            manifest = root.joinpath("manifest.json").read_bytes()
            files = {name: root.joinpath(*name.split("/")).read_bytes() for name in EXPECTED_ZONES}
        except (FileNotFoundError, ModuleNotFoundError, OSError) as exc:
            raise TzdbIntegrityError("installed tzdb bundle is unavailable") from exc
        return cls(manifest, files)

    @property
    def version(self) -> str:
        return self._version

    @property
    def bundle_digest(self) -> str:
        return self._bundle_digest

    def zone(self, name: str) -> ZoneInfo:
        data = self._files.get(name)
        if data is None:
            raise TzdbIntegrityError(f"unknown zone in installed tzdb: {name}")
        cached = self._cache.get(name)
        if cached is None:
            cached = ZoneInfo.from_file(BytesIO(data), key=name)
            self._cache[name] = cached
        return cached
