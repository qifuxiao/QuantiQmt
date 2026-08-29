from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from quantiqmt.live.qmt.readonly_probe import (
    ProbeConfigError,
    ReadonlyProbeConfig,
    RuntimeIdentity,
    load_probe_environment,
    run_probe,
    run_probe_isolated,
)

ACCOUNT_ID = "simulation-account-should-never-leak"


def valid_environment(userdata_path: Path) -> dict[str, str]:
    return {
        "QUANTIQMT_PROFILE": "MINIQMT_SIM_READONLY",
        "QUANTIQMT_QMT_USERDATA_PATH": str(userdata_path),
        "QUANTIQMT_QMT_ACCOUNT_ID": ACCOUNT_ID,
        "QUANTIQMT_QMT_ACCOUNT_TYPE": "STOCK",
        "QUANTIQMT_QMT_SESSION_ID": "12001",
        "QUANTIQMT_QMT_ALLOWED_ACCOUNT_IDS": ACCOUNT_ID,
        "QUANTIQMT_QMT_SIMULATION_ACCOUNT_CONFIRMED": "true",
        "QUANTIQMT_QMT_PROBE_TIMEOUT_SECONDS": "10",
        "QUANTIQMT_QMT_ORDER_SEND_ENABLED": "false",
        "QUANTIQMT_KILL_SWITCH_ENGAGED": "true",
    }


@pytest.mark.unit
@pytest.mark.parametrize(
    ("updates", "reason_code"),
    [
        ({"QUANTIQMT_PROFILE": "MINIQMT_SIM_TRADING"}, "CONFIG_PROFILE_FORBIDDEN"),
        ({"QUANTIQMT_QMT_ACCOUNT_ID": ""}, "CONFIG_ACCOUNT_REQUIRED"),
        (
            {"QUANTIQMT_QMT_ALLOWED_ACCOUNT_IDS": "another-simulation-account"},
            "CONFIG_ACCOUNT_NOT_ALLOWED",
        ),
        (
            {"QUANTIQMT_QMT_ALLOWED_ACCOUNT_IDS": f"{ACCOUNT_ID},{ACCOUNT_ID}"},
            "CONFIG_ACCOUNT_ALLOWLIST_INVALID",
        ),
        (
            {"QUANTIQMT_QMT_SIMULATION_ACCOUNT_CONFIRMED": "false"},
            "CONFIG_SIMULATION_CONFIRMATION_REQUIRED",
        ),
        ({"QUANTIQMT_QMT_ACCOUNT_TYPE": ""}, "CONFIG_ACCOUNT_TYPE_REQUIRED"),
        ({"QUANTIQMT_QMT_SESSION_ID": "0"}, "CONFIG_SESSION_INVALID"),
        ({"QUANTIQMT_QMT_SESSION_ID": "not-an-int"}, "CONFIG_SESSION_INVALID"),
        ({"QUANTIQMT_QMT_PROBE_TIMEOUT_SECONDS": "0"}, "CONFIG_TIMEOUT_INVALID"),
        ({"QUANTIQMT_QMT_PROBE_TIMEOUT_SECONDS": "301"}, "CONFIG_TIMEOUT_INVALID"),
        ({"QUANTIQMT_QMT_ORDER_SEND_ENABLED": "true"}, "CONFIG_ORDER_SEND_FORBIDDEN"),
        ({"QUANTIQMT_KILL_SWITCH_ENGAGED": "false"}, "CONFIG_KILL_SWITCH_REQUIRED"),
    ],
)
def test_configuration_fails_closed(
    tmp_path: Path, updates: Mapping[str, str], reason_code: str
) -> None:
    userdata_path = tmp_path / "userdata_mini"
    userdata_path.mkdir()
    environment = valid_environment(userdata_path)
    environment.update(updates)

    with pytest.raises(ProbeConfigError) as exc_info:
        ReadonlyProbeConfig.from_environment(environment)

    assert exc_info.value.reason_code == reason_code
    assert ACCOUNT_ID not in str(exc_info.value)


@pytest.mark.unit
def test_configuration_requires_userdata_directory(tmp_path: Path) -> None:
    environment = valid_environment(tmp_path / "missing" / "userdata_mini")

    with pytest.raises(ProbeConfigError) as exc_info:
        ReadonlyProbeConfig.from_environment(environment)

    assert exc_info.value.reason_code == "CONFIG_USERDATA_INVALID"
    assert str(tmp_path) not in str(exc_info.value)


class FakeReadonlyFacade:
    def __init__(self, account_id: str = ACCOUNT_ID) -> None:
        self.account_id = account_id
        self.calls: list[str] = []

    def start(self) -> None:
        self.calls.append("start")

    def connect(self) -> int:
        self.calls.append("connect")
        return 0

    def subscribe(self) -> int:
        self.calls.append("subscribe")
        return 0

    def query_account_status(self) -> list[object]:
        self.calls.append("query_account_status")
        return [SimpleNamespace(account_id=self.account_id)]

    def query_asset(self) -> object:
        self.calls.append("query_asset")
        return object()

    def query_positions(self) -> list[object]:
        self.calls.append("query_positions")
        return [object(), object()]

    def query_orders(self) -> list[object]:
        self.calls.append("query_orders")
        return [object()]

    def query_trades(self) -> list[object]:
        self.calls.append("query_trades")
        return []

    def unsubscribe(self) -> None:
        self.calls.append("unsubscribe")

    def stop(self) -> None:
        self.calls.append("stop")


def windows_runtime() -> RuntimeIdentity:
    return RuntimeIdentity(
        platform="Windows",
        python_version="3.12.10",
        xtquant_version="250516.1.1",
    )


@pytest.mark.unit
def test_fake_vendor_uses_only_five_readonly_queries_and_cleanup(tmp_path: Path) -> None:
    userdata_path = tmp_path / "userdata_mini"
    userdata_path.mkdir()
    config = ReadonlyProbeConfig.from_environment(valid_environment(userdata_path))
    facade = FakeReadonlyFacade()

    report = run_probe(config, lambda _: facade, runtime=windows_runtime())

    assert report.passed is True
    assert report.reason_code == "PROBE_OK"
    assert facade.calls == [
        "start",
        "connect",
        "subscribe",
        "query_account_status",
        "query_asset",
        "query_positions",
        "query_orders",
        "query_trades",
        "unsubscribe",
        "stop",
    ]
    assert report.positions_count == 2
    assert report.orders_count == 1
    assert report.trades_count == 0
    assert not any("order_stock" in call or "cancel_order" in call for call in facade.calls)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("runtime", "reason_code"),
    [
        (
            RuntimeIdentity("Linux", "3.12.10", "250516.1.1"),
            "RUNTIME_WINDOWS_REQUIRED",
        ),
        (RuntimeIdentity("Windows", "3.12.10", None), "RUNTIME_XTQUANT_UNAVAILABLE"),
    ],
)
def test_runtime_compatibility_fails_closed(
    tmp_path: Path, runtime: RuntimeIdentity, reason_code: str
) -> None:
    userdata_path = tmp_path / "userdata_mini"
    userdata_path.mkdir()
    config = ReadonlyProbeConfig.from_environment(valid_environment(userdata_path))
    factory_called = False

    def factory(_: ReadonlyProbeConfig) -> FakeReadonlyFacade:
        nonlocal factory_called
        factory_called = True
        return FakeReadonlyFacade()

    report = run_probe(config, factory, runtime=runtime)

    assert report.passed is False
    assert report.reason_code == reason_code
    assert factory_called is False


@pytest.mark.unit
def test_account_identity_mismatch_fails_closed_and_cleans_up(tmp_path: Path) -> None:
    userdata_path = tmp_path / "userdata_mini"
    userdata_path.mkdir()
    config = ReadonlyProbeConfig.from_environment(valid_environment(userdata_path))
    facade = FakeReadonlyFacade(account_id="unexpected-account")

    report = run_probe(config, lambda _: facade, runtime=windows_runtime())

    assert report.passed is False
    assert report.reason_code == "QUERY_ACCOUNT_IDENTITY_MISMATCH"
    assert facade.calls[-2:] == ["unsubscribe", "stop"]


@pytest.mark.unit
def test_public_json_redacts_account_objects_exceptions_and_full_path(tmp_path: Path) -> None:
    userdata_path = tmp_path / "secret-parent" / "userdata_mini"
    userdata_path.mkdir(parents=True)
    config = ReadonlyProbeConfig.from_environment(valid_environment(userdata_path))

    class LeakyFailureFacade(FakeReadonlyFacade):
        def query_asset(self) -> object:
            raise RuntimeError(f"{ACCOUNT_ID} {userdata_path} raw-asset-object")

    report = run_probe(config, lambda _: LeakyFailureFacade(), runtime=windows_runtime())
    encoded = json.dumps(report.to_public_dict(), ensure_ascii=False)

    assert report.reason_code == "QUERY_ASSET_FAILED"
    assert ACCOUNT_ID not in encoded
    assert str(userdata_path) not in encoded
    assert "raw-asset-object" not in encoded
    assert report.userdata_leaf == "userdata_mini"


class FakeProcess:
    def __init__(self) -> None:
        self.started = False
        self.terminated = False
        self.join_timeouts: list[float | None] = []

    def start(self) -> None:
        self.started = True

    def join(self, timeout: float | None = None) -> None:
        self.join_timeouts.append(timeout)

    def is_alive(self) -> bool:
        return not self.terminated

    def terminate(self) -> None:
        self.terminated = True


class EmptyQueue:
    def get(self, *, timeout: float) -> Any:
        assert timeout == 1.0
        raise LookupError


class TimeoutContext:
    def __init__(self) -> None:
        self.process = FakeProcess()

    def Queue(self) -> EmptyQueue:
        return EmptyQueue()

    def Process(self, **_: object) -> FakeProcess:
        return self.process


@pytest.mark.unit
def test_worker_timeout_terminates_process_and_reports_no_success(tmp_path: Path) -> None:
    userdata_path = tmp_path / "userdata_mini"
    userdata_path.mkdir()
    config = ReadonlyProbeConfig.from_environment(valid_environment(userdata_path))
    context = TimeoutContext()

    report = run_probe_isolated(config, context=context)

    assert context.process.started is True
    assert context.process.terminated is True
    assert context.process.join_timeouts == [10.0, 1.0]
    assert report.passed is False
    assert report.reason_code == "PROBE_DEADLINE_EXCEEDED"
    assert report.connected is False
    assert report.subscribed is False
    assert report.asset_queried is False


class DeniedContext:
    def Queue(self) -> EmptyQueue:
        raise PermissionError(f"{ACCOUNT_ID} forbidden-pipe-path")


@pytest.mark.unit
def test_worker_start_failure_is_redacted(tmp_path: Path) -> None:
    userdata_path = tmp_path / "userdata_mini"
    userdata_path.mkdir()
    config = ReadonlyProbeConfig.from_environment(valid_environment(userdata_path))

    report = run_probe_isolated(config, context=DeniedContext())
    encoded = json.dumps(report.to_public_dict())

    assert report.passed is False
    assert report.reason_code == "PROBE_WORKER_START_FAILED"
    assert ACCOUNT_ID not in encoded
    assert "forbidden-pipe-path" not in encoded


@pytest.mark.unit
def test_env_file_is_allowlisted_literal_and_does_not_override_process_env(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "QUANTIQMT_PROFILE=MINIQMT_SIM_READONLY\n"
        "QUANTIQMT_QMT_ACCOUNT_ID=$(not-executed)\n"
        "QUANTIQMT_QMT_SESSION_ID=999\n",
        encoding="utf-8",
    )

    loaded = load_probe_environment(
        env_file, {"QUANTIQMT_QMT_SESSION_ID": "12001", "UNRELATED": "preserved"}
    )

    assert loaded["QUANTIQMT_QMT_ACCOUNT_ID"] == "$(not-executed)"
    assert loaded["QUANTIQMT_QMT_SESSION_ID"] == "12001"
    assert loaded["UNRELATED"] == "preserved"


@pytest.mark.unit
def test_env_file_rejects_unknown_qmt_and_secret_keys(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("QUANTIQMT_QMT_PASSWORD=forbidden\n", encoding="utf-8")

    with pytest.raises(ProbeConfigError) as exc_info:
        load_probe_environment(env_file, {})

    assert exc_info.value.reason_code == "ENV_KEY_FORBIDDEN"
    assert "forbidden" not in str(exc_info.value)


@pytest.mark.unit
def test_probe_source_contains_no_vendor_trading_calls() -> None:
    source = (
        Path(__file__).parents[3] / "src" / "quantiqmt" / "live" / "qmt" / "readonly_probe.py"
    ).read_text(encoding="utf-8")
    forbidden_fragments = (
        ".order_stock(",
        ".order_stock_async(",
        ".cancel_order_stock(",
        ".cancel_order_stock_async(",
        ".cancel_order_stock_sysid(",
        ".cancel_order_stock_sysid_async(",
    )

    assert all(fragment not in source for fragment in forbidden_fragments)
