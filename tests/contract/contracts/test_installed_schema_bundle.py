from __future__ import annotations

import importlib.resources
import os
import subprocess
import sys
import venv
from pathlib import Path

import pytest

from quantiqmt.contracts import SchemaRegistry
from quantiqmt.contracts.bundle import BundleIntegrityError, SchemaBundle
from quantiqmt.contracts.tzdb import FrozenTzdb, TzdbIntegrityError


def test_installed_bundle_serves_every_active_market_route_without_checkout() -> None:
    bundle = SchemaBundle.installed()
    registry = SchemaRegistry()

    expected = {
        "market.tick_received.v1",
        "market.bar_closed.v1",
        "market.quality_changed.v1",
        "market.session_changed.v1",
    }
    assert expected <= set(registry.message_types)
    assert all(
        registry.payload(route, 1)["$schema"].endswith("2020-12/schema") for route in expected
    )
    assert bundle.contract("CONTRACT-MARKET-DATA-V1")["$id"].endswith("market-data:v1")


def test_installed_resources_are_present_and_fail_closed_when_missing_or_tampered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource = importlib.resources.files("quantiqmt.contracts.resources").joinpath(
        "schema-bundle.v1.json"
    )
    assert resource.is_file()

    monkeypatch.setattr(
        "quantiqmt.contracts.bundle._installed_bundle_bytes", lambda: b'{"partial":true}'
    )
    with pytest.raises(BundleIntegrityError):
        SchemaBundle.installed()


def test_installed_tzdb_uses_only_verified_tzif_bytes() -> None:
    tzdb = FrozenTzdb.installed()
    assert tzdb.version == "2026c"
    assert tzdb.zone("Asia/Shanghai").key == "Asia/Shanghai"
    with pytest.raises(TzdbIntegrityError, match="unknown zone"):
        tzdb.zone("Europe/London")


def test_installed_schema_bundle_from_wheel_without_source_checkout(tmp_path: Path) -> None:
    wheels = sorted((Path(__file__).resolve().parents[3] / "dist").glob("quantiqmt-*.whl"))
    if not wheels:
        pytest.skip("wheel is built by the preceding prescribed `poetry build` command")
    environment = tmp_path / "venv"
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    clean_environment = dict(os.environ)
    clean_environment.pop("PYTHONPATH", None)
    subprocess.run(
        [str(python), "-m", "pip", "install", "--no-deps", str(wheels[-1])],
        cwd=tmp_path,
        env=clean_environment,
        check=True,
        capture_output=True,
        text=True,
    )
    probe = (
        "from quantiqmt.contracts import SchemaRegistry; "
        "from quantiqmt.contracts.tzdb import FrozenTzdb; "
        "r=SchemaRegistry(); "
        "assert r.payload('market.tick_received.v1',1)['$id'].endswith(':v1'); "
        "assert FrozenTzdb.installed().zone('UTC').key == 'UTC'"
    )
    subprocess.run(
        [str(python), "-I", "-c", probe],
        cwd=tmp_path,
        env=clean_environment,
        check=True,
        capture_output=True,
        text=True,
    )

    locate = "import quantiqmt.contracts.resources as r; print(next(iter(r.__path__)))"
    resource_root = Path(
        subprocess.run(
            [str(python), "-I", "-c", locate],
            cwd=tmp_path,
            env=clean_environment,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    bundle = resource_root / "schema-bundle.v1.json"
    original = bundle.read_bytes()
    bundle.write_bytes(b'{"partial":true}')
    failure_probe = (
        "from quantiqmt.contracts.bundle import SchemaBundle,BundleIntegrityError; "
        "\ntry: SchemaBundle.installed()\nexcept BundleIntegrityError: raise SystemExit(0)\n"
        "raise SystemExit(1)"
    )
    subprocess.run(
        [str(python), "-I", "-c", failure_probe],
        cwd=tmp_path,
        env=clean_environment,
        check=True,
        capture_output=True,
        text=True,
    )
    bundle.write_bytes(original)
