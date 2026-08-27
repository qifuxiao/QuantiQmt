"""Generation and fail-closed loading of the installed immutable contract bundle."""

from __future__ import annotations

import hashlib
import importlib.resources
import json
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, cast

BUNDLE_SCHEMA_VERSION = 1
EXPECTED_MANIFEST_VERSION = "0.13.0"
_MANIFEST_VERSION = re.compile(r"(?m)^  version:\s*([^\s#]+)\s*$")
_CONTRACT_ID = re.compile(r"^    - id:\s*([^\s#]+)\s*$")
_CONTRACT_PATH = re.compile(r"^      path:\s*([^\s#]+)\s*$")
_CATALOG_ENTRY = re.compile(r"name:\s*([^,}]+).*?schema:\s*([^,}]+).*?status:\s*active")


class BundleIntegrityError(ValueError):
    """The installed schema bundle is absent, partial, mismatched, or tampered."""


@dataclass(frozen=True, slots=True)
class SchemaBundle:
    """Verified immutable contract snapshot generated from ``spec/manifest.yaml``."""

    _document: Mapping[str, Any]

    @classmethod
    def installed(cls) -> SchemaBundle:
        """Load only the package resource; no source-checkout fallback is permitted."""
        return cls.from_bytes(_installed_bundle_bytes())

    @classmethod
    def from_bytes(cls, raw: bytes) -> SchemaBundle:
        try:
            decoded = raw.decode("utf-8-sig")
            document = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BundleIntegrityError("schema bundle is missing or malformed") from exc
        if not isinstance(document, dict):
            raise BundleIntegrityError("schema bundle root must be an object")
        _verify_bundle(document)
        return cls(cast(Mapping[str, Any], _deep_freeze(document)))

    @property
    def manifest_version(self) -> str:
        return cast(str, self._document["manifest_version"])

    @property
    def bundle_digest(self) -> str:
        return cast(str, self._document["bundle_digest"])

    @property
    def contract_ids(self) -> tuple[str, ...]:
        contracts = cast(tuple[Mapping[str, Any], ...], self._document["contracts"])
        return tuple(cast(str, entry["id"]) for entry in contracts)

    @property
    def routes(self) -> tuple[Mapping[str, Any], ...]:
        return cast(tuple[Mapping[str, Any], ...], self._document["routes"])

    def contract(self, contract_id: str) -> Any:
        contracts = cast(tuple[Mapping[str, Any], ...], self._document["contracts"])
        for entry in contracts:
            if entry["id"] == contract_id:
                return entry["document"]
        raise BundleIntegrityError(f"contract is not present in installed bundle: {contract_id}")

    def contract_by_path(self, path: str) -> Any:
        contracts = cast(tuple[Mapping[str, Any], ...], self._document["contracts"])
        for entry in contracts:
            if entry["path"] == path:
                return entry["document"]
        for route in self.routes:
            if route["path"] == path:
                return route["document"]
        raise BundleIntegrityError(f"contract path is not present in installed bundle: {path}")

    def to_bytes(self) -> bytes:
        return _serialize_bundle(_deep_thaw(self._document))


def build_schema_bundle(spec_root: Path) -> SchemaBundle:
    """Generate and verify a bundle from the reviewed manifest contract index.

    This function is a build/test boundary. Runtime construction uses
    :meth:`SchemaBundle.installed` and never calls it.
    """
    manifest_path = spec_root / "manifest.yaml"
    try:
        manifest_text = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BundleIntegrityError("reviewed spec manifest is unavailable") from exc
    version_match = _MANIFEST_VERSION.search(manifest_text)
    if version_match is None:
        raise BundleIntegrityError("spec manifest version is missing")
    manifest_version = version_match.group(1)
    if manifest_version != EXPECTED_MANIFEST_VERSION:
        raise BundleIntegrityError("spec manifest version does not match installed runtime")

    indexed = _parse_contract_index(manifest_text)
    contracts: list[dict[str, Any]] = []
    indexed_paths: set[str] = set()
    for contract_id, relative in indexed:
        normalized = _safe_relative(relative)
        if normalized in indexed_paths:
            raise BundleIntegrityError(f"duplicate contract path: {normalized}")
        indexed_paths.add(normalized)
        path = spec_root / Path(*PurePosixPath(normalized).parts)
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise BundleIntegrityError(f"contract path is missing: {normalized}") from exc
        if raw.startswith(b"\xef\xbb\xbf"):
            raise BundleIntegrityError(f"contract contains forbidden UTF-8 BOM: {normalized}")
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BundleIntegrityError(f"contract is not UTF-8: {normalized}") from exc
        document = _parse_contract_document(normalized, content)
        contracts.append(
            {
                "id": contract_id,
                "path": normalized,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "document_sha256": _bundle_projection_digest(document),
                "content": content,
                "document": document,
            }
        )

    documents_by_path: dict[str, Any] = {
        cast(str, entry["path"]): entry["document"]
        for entry in contracts
        if cast(str, entry["path"]).endswith(".schema.json")
    }
    catalog = next((entry for entry in contracts if entry["id"] == "CONTRACT-CATALOG"), None)
    if catalog is None:
        raise BundleIntegrityError("CONTRACT-CATALOG is missing from manifest")
    routes = _parse_active_routes(cast(str, catalog["content"]), spec_root)
    for route in routes:
        route_path = cast(str, route["path"])
        documents_by_path.setdefault(route_path, route["document"])

    documents_by_id: dict[str, Any] = {}
    for schema_path, schema in documents_by_path.items():
        if not isinstance(schema, Mapping):
            raise BundleIntegrityError(f"JSON Schema root must be an object: {schema_path}")
        schema_id = schema.get("$id")
        if isinstance(schema_id, str):
            if schema_id in documents_by_id:
                raise BundleIntegrityError(f"duplicate JSON Schema $id: {schema_id}")
            documents_by_id[schema_id] = schema
    for schema_path, schema in documents_by_path.items():
        _validate_schema_references(schema, schema_path, documents_by_path, documents_by_id)

    bundle_document: dict[str, Any] = {
        "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
        "manifest_version": manifest_version,
        "contracts": contracts,
        "routes": routes,
    }
    bundle_document["bundle_digest"] = _bundle_projection_digest(bundle_document)
    return SchemaBundle.from_bytes(_serialize_bundle(bundle_document))


def write_schema_bundle(spec_root: Path, destination: Path) -> None:
    """Write the mechanically generated canonical resource."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(build_schema_bundle(spec_root).to_bytes())


def verify_schema_bundle_parity(spec_root: Path, installed: SchemaBundle | None = None) -> None:
    """Fail when the reviewed source index and generated installed artifact diverge."""
    generated = build_schema_bundle(spec_root)
    accepted = installed or SchemaBundle.installed()
    if generated.to_bytes() != accepted.to_bytes():
        raise BundleIntegrityError("generated schema bundle parity mismatch")


def _installed_bundle_bytes() -> bytes:
    try:
        resource = importlib.resources.files("quantiqmt.contracts.resources").joinpath(
            "schema-bundle.v1.json"
        )
        return resource.read_bytes()
    except (FileNotFoundError, ModuleNotFoundError, OSError) as exc:
        raise BundleIntegrityError("installed schema bundle is unavailable") from exc


def _parse_contract_index(manifest: str) -> list[tuple[str, str]]:
    lines = manifest.splitlines()
    try:
        start = lines.index("  contracts:") + 1
    except ValueError as exc:
        raise BundleIntegrityError("spec manifest contract index is missing") from exc
    result: list[tuple[str, str]] = []
    identifiers: set[str] = set()
    pending: str | None = None
    for line in lines[start:]:
        if line.startswith("  ") and not line.startswith("    "):
            break
        id_match = _CONTRACT_ID.fullmatch(line)
        if id_match is not None:
            if pending is not None:
                raise BundleIntegrityError(f"contract path is missing for {pending}")
            pending = id_match.group(1)
            if pending in identifiers:
                raise BundleIntegrityError(f"duplicate contract id: {pending}")
            identifiers.add(pending)
            continue
        path_match = _CONTRACT_PATH.fullmatch(line)
        if path_match is not None and pending is not None:
            result.append((pending, path_match.group(1)))
            pending = None
    if pending is not None:
        raise BundleIntegrityError(f"contract path is missing for {pending}")
    if not result:
        raise BundleIntegrityError("spec manifest contract index is empty")
    return result


def _parse_active_routes(catalog: str, spec_root: Path) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    names: set[str] = set()
    for line in catalog.splitlines():
        match = _CATALOG_ENTRY.search(line)
        if match is None:
            continue
        name = match.group(1).strip()
        path = _safe_relative("contracts/" + match.group(2).strip())
        if name in names:
            raise BundleIntegrityError(f"duplicate active route: {name}")
        names.add(name)
        try:
            raw = (spec_root / Path(*PurePosixPath(path).parts)).read_bytes()
        except OSError as exc:
            raise BundleIntegrityError(f"active route schema is missing: {path}") from exc
        if raw.startswith(b"\xef\xbb\xbf"):
            raise BundleIntegrityError(f"active route contains forbidden UTF-8 BOM: {path}")
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BundleIntegrityError(f"active route is not UTF-8: {path}") from exc
        document = _parse_contract_document(path, content)
        routes.append(
            {
                "message_type": name,
                "path": path,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "document_sha256": _bundle_projection_digest(document),
                "content": content,
                "document": document,
            }
        )
    if not routes:
        raise BundleIntegrityError("catalog contains no active message routes")
    return routes


def _parse_contract_document(path: str, content: str) -> Any:
    if path.endswith(".json"):
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise BundleIntegrityError(f"contract JSON is malformed: {path}") from exc
    if path.endswith((".yaml", ".yml")):
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - build environment guarantee
            raise BundleIntegrityError("PyYAML is required only to generate the bundle") from exc
        try:
            return yaml.safe_load(content)
        except yaml.YAMLError as exc:
            raise BundleIntegrityError(f"contract YAML is malformed: {path}") from exc
    return content


def _validate_schema_references(
    document: Any,
    path: str,
    documents_by_path: Mapping[str, Any],
    documents_by_id: Mapping[str, Any],
) -> None:
    if not isinstance(document, Mapping):
        raise BundleIntegrityError(f"JSON Schema root must be an object: {path}")
    for reference in _walk_refs(document):
        target_path, separator, fragment = reference.partition("#")
        target: Any = document
        if target_path:
            if target_path.startswith("urn:"):
                target = documents_by_id.get(target_path)
            else:
                normalized = _safe_relative(str(PurePosixPath(path).parent.joinpath(target_path)))
                target = documents_by_path.get(normalized)
            if target is None:
                raise BundleIntegrityError(f"unresolved schema reference: {path} -> {reference}")
        if separator:
            _resolve_json_pointer(target, fragment, path, reference)


def _walk_refs(value: Any) -> Iterator[str]:
    if isinstance(value, Mapping):
        reference = value.get("$ref")
        if isinstance(reference, str):
            yield reference
        for item in value.values():
            yield from _walk_refs(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_refs(item)


def _resolve_json_pointer(document: Any, fragment: str, path: str, reference: str) -> None:
    if fragment == "":
        return
    if not fragment.startswith("/"):
        raise BundleIntegrityError(f"unsupported schema reference: {path} -> {reference}")
    current = document
    for raw_part in fragment[1:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, Mapping) or part not in current:
            raise BundleIntegrityError(f"unresolved schema reference: {path} -> {reference}")
        current = current[part]


def _safe_relative(value: str) -> str:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise BundleIntegrityError(f"unsafe contract path: {value}")
    return path.as_posix()


def _verify_bundle(document: dict[str, Any]) -> None:
    if document.get("bundle_schema_version") != BUNDLE_SCHEMA_VERSION:
        raise BundleIntegrityError("schema bundle version mismatch")
    if document.get("manifest_version") != EXPECTED_MANIFEST_VERSION:
        raise BundleIntegrityError("schema manifest version mismatch")
    contracts = document.get("contracts")
    routes = document.get("routes")
    digest = document.get("bundle_digest")
    if not isinstance(contracts, list) or not contracts or not isinstance(routes, list):
        raise BundleIntegrityError("schema bundle is partial")
    ids: set[str] = set()
    paths: set[str] = set()
    for entry in contracts:
        if not isinstance(entry, dict):
            raise BundleIntegrityError("schema bundle contract entry is malformed")
        try:
            contract_id = entry["id"]
            path = entry["path"]
            content = entry["content"]
            expected_content = entry["sha256"]
            expected_document = entry["document_sha256"]
            parsed = entry["document"]
        except KeyError as exc:
            raise BundleIntegrityError("schema bundle contract entry is partial") from exc
        if not all(isinstance(item, str) for item in (contract_id, path, content)):
            raise BundleIntegrityError("schema bundle contract identity is malformed")
        if contract_id in ids or path in paths:
            raise BundleIntegrityError("schema bundle contains duplicate identity or path")
        ids.add(contract_id)
        paths.add(path)
        if hashlib.sha256(content.encode("utf-8")).hexdigest() != expected_content:
            raise BundleIntegrityError(f"contract content digest mismatch: {contract_id}")
        if _bundle_projection_digest(parsed) != expected_document:
            raise BundleIntegrityError(f"contract document digest mismatch: {contract_id}")
    route_names: set[str] = set()
    for route in routes:
        if not isinstance(route, dict):
            raise BundleIntegrityError("schema bundle route is malformed")
        name = route.get("message_type")
        path = route.get("path")
        content = route.get("content")
        route_document = route.get("document")
        if not isinstance(name, str) or not isinstance(path, str) or not isinstance(content, str):
            raise BundleIntegrityError("schema bundle route is missing its canonical contract")
        if name in route_names:
            raise BundleIntegrityError("schema bundle contains duplicate route")
        route_names.add(name)
        if hashlib.sha256(content.encode("utf-8")).hexdigest() != route.get("sha256"):
            raise BundleIntegrityError(f"route content digest mismatch: {name}")
        if _bundle_projection_digest(route_document) != route.get("document_sha256"):
            raise BundleIntegrityError(f"route document digest mismatch: {name}")
    projection = dict(document)
    projection.pop("bundle_digest", None)
    if not isinstance(digest, str) or _bundle_projection_digest(projection) != digest:
        raise BundleIntegrityError("schema bundle digest mismatch")


def _serialize_bundle(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _bundle_projection_digest(value: Any) -> str:
    """Hash generated metadata, which may include non-market YAML ratio floats."""
    try:
        payload = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise BundleIntegrityError("contract document is not finite JSON-compatible data") from exc
    return hashlib.sha256(payload).hexdigest()


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    return value


def _deep_thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _deep_thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_deep_thaw(item) for item in value]
    return value
