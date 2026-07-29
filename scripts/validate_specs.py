"""Validate normative specifications and AI task metadata."""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from jsonschema.validators import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SPEC_ROOT = ROOT / "spec"
TASK_ROOT = ROOT / "tasks"


def load_yaml(path: Path) -> Any:
    """Load one YAML document."""
    with path.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def load_json(path: Path) -> Any:
    """Load one JSON document."""
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def extract_front_matter(path: Path) -> dict[str, Any]:
    """Parse YAML front matter from a Markdown task."""
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\s*\r?\n(.*?)\r?\n---\s*\r?\n", text, re.DOTALL)
    if match is None:
        raise ValueError("missing YAML front matter")
    value = yaml.safe_load(match.group(1))
    if not isinstance(value, dict):
        raise ValueError("front matter must be a mapping")
    return value


def manifest_entries(manifest: dict[str, Any]) -> dict[str, Path]:
    """Return all manifest IDs and their resolved paths."""
    result: dict[str, Path] = {}
    catalogs = manifest.get("catalogs")
    if not isinstance(catalogs, dict):
        return result
    for entries in catalogs.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            spec_id = entry.get("id")
            relative_path = entry.get("path")
            if isinstance(spec_id, str) and isinstance(relative_path, str):
                result[spec_id] = SPEC_ROOT / relative_path
    return result


def has_cycle(graph: dict[str, list[str]]) -> bool:
    """Return True when a dependency graph contains a cycle."""
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(dependency) for dependency in graph.get(node, [])):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)


def task_files() -> Iterable[Path]:
    """Yield executable task Markdown files."""
    for state in ("backlog", "active", "completed"):
        yield from sorted((TASK_ROOT / state).glob("TASK-*.md"))


def validate_json_schemas(errors: list[str]) -> None:
    for path in sorted(SPEC_ROOT.rglob("*.schema.json")):
        try:
            schema = load_json(path)
            Draft202012Validator.check_schema(schema)
        except Exception as exc:  # validation boundary intentionally reports every file
            errors.append(f"{path.relative_to(ROOT)}: invalid JSON Schema: {exc}")


def validate_yaml_files(errors: list[str]) -> None:
    for base in (SPEC_ROOT, TASK_ROOT):
        for path in sorted(base.rglob("*.yaml")):
            try:
                load_yaml(path)
            except Exception as exc:
                errors.append(f"{path.relative_to(ROOT)}: invalid YAML: {exc}")


def validate_manifest(errors: list[str]) -> dict[str, Path]:
    manifest = load_yaml(SPEC_ROOT / "manifest.yaml")
    if not isinstance(manifest, dict):
        errors.append("spec/manifest.yaml: root must be a mapping")
        return {}
    entries = manifest_entries(manifest)
    if not entries:
        errors.append("spec/manifest.yaml: no catalog entries")
    for spec_id, path in entries.items():
        if not path.is_file():
            errors.append(f"spec/manifest.yaml: {spec_id} path does not exist: {path}")
    return entries


def validate_tasks(specs: dict[str, Path], errors: list[str]) -> None:
    tasks: dict[str, dict[str, Any]] = {}
    task_paths: dict[str, Path] = {}
    for path in task_files():
        try:
            task = extract_front_matter(path)
        except Exception as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
            continue
        task_id = task.get("id")
        if not isinstance(task_id, str) or re.fullmatch(r"TASK-\d{3}", task_id) is None:
            errors.append(f"{path.relative_to(ROOT)}: invalid task id")
            continue
        if task_id in tasks:
            errors.append(f"duplicate task id: {task_id}")
        tasks[task_id] = task
        task_paths[task_id] = path
        for field in ("status", "depends_on", "spec_refs", "allowed_paths", "forbidden_paths"):
            if field not in task:
                errors.append(f"{path.relative_to(ROOT)}: missing {field}")
        for spec_id in task.get("spec_refs", []):
            if spec_id not in specs:
                errors.append(f"{path.relative_to(ROOT)}: unknown spec ref {spec_id}")
        verification = task.get("verification")
        if not isinstance(verification, dict) or not verification.get("commands"):
            errors.append(f"{path.relative_to(ROOT)}: verification.commands must not be empty")

    graph: dict[str, list[str]] = {}
    for task_id, task in tasks.items():
        dependencies = task.get("depends_on", [])
        if not isinstance(dependencies, list):
            errors.append(f"{task_paths[task_id].relative_to(ROOT)}: depends_on must be a list")
            continue
        graph[task_id] = [str(value) for value in dependencies]
        for dependency in graph[task_id]:
            if dependency not in tasks:
                unknown_dep_path = task_paths[task_id].relative_to(ROOT)
                errors.append(f"{unknown_dep_path}: unknown dependency {dependency}")
    if has_cycle(graph):
        errors.append("tasks: dependency graph contains a cycle")

    index = load_yaml(TASK_ROOT / "index.yaml")
    indexed = index.get("tasks", []) if isinstance(index, dict) else []
    indexed_ids: set[str] = set()
    for entry in indexed:
        if not isinstance(entry, dict):
            errors.append("tasks/index.yaml: each task entry must be a mapping")
            continue
        task_id = entry.get("id")
        indexed_path = entry.get("path")
        if isinstance(task_id, str):
            indexed_ids.add(task_id)
        if not isinstance(indexed_path, str) or not (TASK_ROOT / indexed_path).is_file():
            errors.append(f"tasks/index.yaml: missing path for {task_id}: {indexed_path}")
        if task_id in tasks and entry.get("status") != tasks[task_id].get("status"):
            errors.append(f"tasks/index.yaml: status mismatch for {task_id}")
    missing = set(tasks) - indexed_ids
    extra = indexed_ids - set(tasks)
    if missing:
        errors.append(f"tasks/index.yaml: unindexed tasks: {sorted(missing)}")
    if extra:
        errors.append(f"tasks/index.yaml: entries without task files: {sorted(extra)}")


def validate_error_catalog(errors: list[str]) -> None:
    catalog = load_yaml(SPEC_ROOT / "contracts" / "errors" / "catalog.yaml")
    entries = catalog.get("errors", []) if isinstance(catalog, dict) else []
    codes: set[str] = set()
    names: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("error catalog: each entry must be a mapping")
            continue
        code = entry.get("code")
        name = entry.get("name")
        if not isinstance(code, str) or re.fullmatch(r"QQ-[A-Z]+-\d{4}", code) is None:
            errors.append(f"error catalog: invalid code {code}")
        elif code in codes:
            errors.append(f"error catalog: duplicate code {code}")
        else:
            codes.add(code)
        if not isinstance(name, str) or not name:
            errors.append(f"error catalog: invalid name {name}")
        elif name in names:
            errors.append(f"error catalog: duplicate name {name}")
        else:
            names.add(name)


def validate_message_catalog(errors: list[str]) -> None:
    catalog_path = SPEC_ROOT / "contracts" / "catalog.yaml"
    catalog = load_yaml(catalog_path)
    messages = catalog.get("messages", []) if isinstance(catalog, dict) else []
    names: set[str] = set()
    for entry in messages:
        if not isinstance(entry, dict):
            errors.append("contract catalog: each message must be a mapping")
            continue
        name = entry.get("name")
        status = entry.get("status")
        schema = entry.get("schema")
        if (
            not isinstance(name, str)
            or re.fullmatch(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.v[1-9][0-9]*", name) is None
        ):
            errors.append(f"contract catalog: invalid message name {name}")
        elif name in names:
            errors.append(f"contract catalog: duplicate message name {name}")
        else:
            names.add(name)
        if status not in {"active", "planned", "deprecated"}:
            errors.append(f"contract catalog: invalid status for {name}: {status}")
        if status == "active":
            if not isinstance(schema, str):
                errors.append(f"contract catalog: active message {name} requires schema")
            elif not (catalog_path.parent / schema).is_file():
                errors.append(f"contract catalog: schema does not exist for {name}: {schema}")


def validate_state_machines(errors: list[str]) -> None:
    for path in sorted((SPEC_ROOT / "state-machines").glob("*.yaml")):
        document = load_yaml(path)
        machine = document.get("machine") if isinstance(document, dict) else None
        if not isinstance(machine, dict):
            errors.append(f"{path.relative_to(ROOT)}: missing machine mapping")
            continue
        states = machine.get("states")
        initial = machine.get("initial")
        transitions = machine.get("transitions")
        if not isinstance(states, dict) or initial not in states:
            errors.append(f"{path.relative_to(ROOT)}: invalid initial state")
            continue
        if not isinstance(transitions, list):
            errors.append(f"{path.relative_to(ROOT)}: transitions must be a list")
            continue
        seen: set[tuple[str, str, str]] = set()
        for transition in transitions:
            if not isinstance(transition, dict):
                errors.append(f"{path.relative_to(ROOT)}: transition must be a mapping")
                continue
            source = transition.get("from")
            event = transition.get("event")
            target = transition.get("to")
            if source not in states or target not in states or not isinstance(event, str):
                errors.append(f"{path.relative_to(ROOT)}: invalid transition {transition}")
                continue
            key = (str(source), event, str(target))
            if key in seen:
                errors.append(f"{path.relative_to(ROOT)}: duplicate transition {key}")
            seen.add(key)


def validate_markdown_links(errors: list[str]) -> None:
    pattern = re.compile(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)")
    for path in sorted(ROOT.rglob("*.md")):
        if any(part in {".git", ".venv"} for part in path.parts):
            continue
        for target in pattern.findall(path.read_text(encoding="utf-8")):
            if re.match(r"^(https?://|mailto:)", target):
                continue
            if not (path.parent / target).resolve().exists():
                errors.append(f"{path.relative_to(ROOT)}: broken link {target}")


def main() -> int:
    errors: list[str] = []
    validate_yaml_files(errors)
    validate_json_schemas(errors)
    specs = validate_manifest(errors)
    validate_tasks(specs, errors)
    validate_error_catalog(errors)
    validate_message_catalog(errors)
    validate_state_machines(errors)
    validate_markdown_links(errors)
    if errors:
        print("Specification validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Specification validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
