from __future__ import annotations

import os
from pathlib import Path

import pytest

from quantiqmt.live.qmt.readonly_probe import (
    PROBE_ENV_KEYS,
    ProbeConfigError,
    ReadonlyProbeConfig,
    detect_runtime_identity,
    run_probe_isolated,
)


def require_explicit_live_config() -> ReadonlyProbeConfig:
    configured_probe_keys = PROBE_ENV_KEYS.intersection(os.environ)
    if not configured_probe_keys:
        pytest.skip("requires explicit TASK-055 Mini QMT simulation environment")
    try:
        return ReadonlyProbeConfig.from_environment(os.environ)
    except ProbeConfigError as exc:
        pytest.fail(
            "TASK-055 live configuration is present but incomplete or unsafe; "
            f"probe correctly failed closed with {exc.reason_code}"
        )


@pytest.mark.integration
def test_local_python_xtquant_and_userdata_environment() -> None:
    config = require_explicit_live_config()
    runtime = detect_runtime_identity()

    assert runtime.platform == "Windows"
    assert runtime.python_version.startswith("3.12.")
    assert runtime.xtquant_version == "250516.1.1"

    assert config.userdata_path.name == "userdata_mini"
    assert config.userdata_path.is_dir()


@pytest.mark.integration
def test_local_miniqmt_readonly_connection_and_queries() -> None:
    config = require_explicit_live_config()
    report = run_probe_isolated(config)

    assert report.passed, report.reason_code
    assert report.connected
    assert report.subscribed
    assert report.account_status_queried
    assert report.asset_queried
    assert report.positions_queried
    assert report.orders_queried
    assert report.trades_queried
    assert report.userdata_leaf == Path(config.userdata_path).name
