from __future__ import annotations

import ast
import json
import subprocess
import sys
import threading
import time
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import quantiqmt.live.qmt.readonly_probe as probe_module
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
        ({"QUANTIQMT_QMT_ACCOUNT_TYPE": "CREDIT"}, "CONFIG_ACCOUNT_TYPE_FORBIDDEN"),
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
    def __init__(
        self,
        account_id: str = ACCOUNT_ID,
        *,
        account_type: int = 2,
        account_status: int = 0,
        extra_statuses: list[object] | None = None,
    ) -> None:
        self.account_id = account_id
        self.account_type = account_type
        self.account_status = account_status
        self.extra_statuses = extra_statuses or []
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
        return [
            SimpleNamespace(
                account_id=self.account_id,
                account_type=self.account_type,
                status=self.account_status,
            ),
            *self.extra_statuses,
        ]

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
@pytest.mark.parametrize(
    ("facade", "reason_code"),
    [
        (FakeReadonlyFacade(account_type=3), "QUERY_ACCOUNT_TYPE_MISMATCH"),
        (FakeReadonlyFacade(account_status=3), "QUERY_ACCOUNT_STATUS_FAILED"),
        (
            FakeReadonlyFacade(
                extra_statuses=[SimpleNamespace(account_id="other", account_type=2, status=0)]
            ),
            "QUERY_ACCOUNT_IDENTITY_AMBIGUOUS",
        ),
    ],
)
def test_account_status_must_be_exact_and_healthy(
    tmp_path: Path, facade: FakeReadonlyFacade, reason_code: str
) -> None:
    userdata_path = tmp_path / "userdata_mini"
    userdata_path.mkdir()
    config = ReadonlyProbeConfig.from_environment(valid_environment(userdata_path))

    report = run_probe(config, lambda _: facade, runtime=windows_runtime())

    assert report.passed is False
    assert report.reason_code == reason_code


@pytest.mark.unit
def test_closed_market_account_status_is_safe_for_readonly_queries(tmp_path: Path) -> None:
    userdata_path = tmp_path / "userdata_mini"
    userdata_path.mkdir()
    config = ReadonlyProbeConfig.from_environment(valid_environment(userdata_path))
    facade = FakeReadonlyFacade(account_status=6)

    report = run_probe(config, lambda _: facade, runtime=windows_runtime())

    assert report.passed is True
    assert report.asset_queried is True
    assert report.positions_queried is True


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

    def kill(self) -> None:
        self.terminated = True

    def close(self) -> None:
        return


class EmptyQueue:
    def get(self, *, timeout: float) -> Any:
        assert timeout == 1.0
        raise LookupError

    def cancel_join_thread(self) -> None:
        return

    def close(self) -> None:
        return


class FakeLaunchGate:
    def __init__(self) -> None:
        self.open = False

    def set(self) -> None:
        self.open = True

    def wait(self, timeout: float) -> bool:
        return self.open


class TimeoutContext:
    def __init__(self) -> None:
        self.process = FakeProcess()

    def Queue(self) -> EmptyQueue:
        return EmptyQueue()

    def Event(self) -> FakeLaunchGate:
        return FakeLaunchGate()

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
    assert len(context.process.join_timeouts) == 2
    assert 0 < context.process.join_timeouts[0] <= 10.0
    assert context.process.join_timeouts[1] == 1.0
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


class StubbornProcess(FakeProcess):
    def __init__(self) -> None:
        super().__init__()
        self.killed = False

    def terminate(self) -> None:
        return

    def kill(self) -> None:
        self.killed = True
        self.terminated = True


class StubbornContext(TimeoutContext):
    def __init__(self) -> None:
        self.process = StubbornProcess()


class TerminateErrorProcess(StubbornProcess):
    def terminate(self) -> None:
        raise OSError("terminate failed with sensitive process detail")


class TerminateErrorContext(TimeoutContext):
    def __init__(self) -> None:
        self.process = TerminateErrorProcess()


@pytest.mark.unit
def test_timeout_escalates_to_kill_and_confirms_worker_death(tmp_path: Path) -> None:
    userdata_path = tmp_path / "userdata_mini"
    userdata_path.mkdir()
    config = ReadonlyProbeConfig.from_environment(valid_environment(userdata_path))
    context = StubbornContext()

    report = run_probe_isolated(config, context=context)

    assert context.process.killed is True
    assert context.process.is_alive() is False
    assert report.reason_code == "PROBE_DEADLINE_EXCEEDED"


@pytest.mark.unit
def test_terminate_error_still_escalates_to_kill(tmp_path: Path) -> None:
    userdata_path = tmp_path / "userdata_mini"
    userdata_path.mkdir()
    config = ReadonlyProbeConfig.from_environment(valid_environment(userdata_path))
    context = TerminateErrorContext()

    report = run_probe_isolated(config, context=context)

    assert context.process.killed is True
    assert context.process.is_alive() is False
    assert report.reason_code == "PROBE_DEADLINE_EXCEEDED"


class SlowStartProcess(FakeProcess):
    def __init__(self) -> None:
        super().__init__()
        self.stop_observed = threading.Event()

    def start(self) -> None:
        time.sleep(0.2)
        self.started = True

    def terminate(self) -> None:
        super().terminate()
        self.stop_observed.set()

    def kill(self) -> None:
        super().kill()
        self.stop_observed.set()


class SlowStartContext(TimeoutContext):
    def __init__(self) -> None:
        self.process = SlowStartProcess()


@pytest.mark.unit
def test_blocked_process_start_is_bounded_and_late_worker_is_killed(tmp_path: Path) -> None:
    userdata_path = tmp_path / "userdata_mini"
    userdata_path.mkdir()
    base_config = ReadonlyProbeConfig.from_environment(valid_environment(userdata_path))
    config = replace(base_config, timeout_seconds=0.05)
    context = SlowStartContext()
    started_at = time.monotonic()

    report = run_probe_isolated(config, context=context)
    elapsed = time.monotonic() - started_at

    assert elapsed < 0.15
    assert report.reason_code == "PROBE_DEADLINE_EXCEEDED"
    if sys.platform == "win32":
        with pytest.raises(probe_module.SessionMutexError) as exc_info:
            probe_module._acquire_session_mutex(config)
        assert exc_info.value.reason_code == "PROBE_SESSION_IN_USE"
    assert context.process.stop_observed.wait(timeout=1.0)
    assert context.process.is_alive() is False
    if sys.platform == "win32":
        release_deadline = time.monotonic() + 1.0
        while True:
            try:
                mutex = probe_module._acquire_session_mutex(config)
                break
            except probe_module.SessionMutexError as exc:
                assert exc.reason_code == "PROBE_SESSION_IN_USE"
                if time.monotonic() >= release_deadline:
                    pytest.fail("late-start cleanup did not release the session mutex")
                time.sleep(0.01)
        mutex.release()


class CloseFailureQueue(EmptyQueue):
    def __init__(self) -> None:
        self.close_called = False

    def cancel_join_thread(self) -> None:
        raise OSError("queue cleanup failed with sensitive detail")

    def close(self) -> None:
        self.close_called = True


@pytest.mark.unit
def test_resource_cleanup_failure_downgrades_success_report(tmp_path: Path) -> None:
    userdata_path = tmp_path / "userdata_mini"
    userdata_path.mkdir()
    config = ReadonlyProbeConfig.from_environment(valid_environment(userdata_path))
    success = run_probe(config, lambda _: FakeReadonlyFacade(), runtime=windows_runtime())
    process = FakeProcess()
    process.terminated = True
    output_queue = CloseFailureQueue()

    report = probe_module._finalize_process_report(success, process, output_queue)

    assert report.passed is False
    assert report.reason_code == "PROBE_RESOURCE_CLEANUP_FAILED"
    assert output_queue.close_called is True


@pytest.mark.unit
def test_session_mutex_conflict_fails_before_process_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    userdata_path = tmp_path / "userdata_mini"
    userdata_path.mkdir()
    config = ReadonlyProbeConfig.from_environment(valid_environment(userdata_path))
    context = TimeoutContext()

    def conflict(_: ReadonlyProbeConfig) -> object:
        raise probe_module.SessionMutexError("PROBE_SESSION_IN_USE")

    monkeypatch.setattr(probe_module, "_acquire_session_mutex", conflict)
    report = run_probe_isolated(config, context=context)

    assert report.reason_code == "PROBE_SESSION_IN_USE"
    assert context.process.started is False


@pytest.mark.unit
@pytest.mark.skipif(sys.platform != "win32", reason="Mini QMT mutex is Windows-only")
def test_windows_named_mutex_rejects_same_userdata_and_session(tmp_path: Path) -> None:
    userdata_path = tmp_path / "userdata_mini"
    userdata_path.mkdir()
    config = ReadonlyProbeConfig.from_environment(valid_environment(userdata_path))
    mutex = probe_module._acquire_session_mutex(config)

    try:
        with pytest.raises(probe_module.SessionMutexError) as exc_info:
            probe_module._acquire_session_mutex(config)
        assert exc_info.value.reason_code == "PROBE_SESSION_IN_USE"
    finally:
        mutex.release()


@pytest.mark.unit
def test_real_probe_factory_has_no_public_default() -> None:
    assert run_probe.__defaults__ is None


@pytest.mark.unit
def test_child_process_output_is_suppressed_at_file_descriptor_level() -> None:
    sensitive = f"{ACCOUNT_ID}-native-output"
    code = (
        "import os,sys; "
        "from quantiqmt.live.qmt.readonly_probe import _isolate_worker_output; "
        "sink=_isolate_worker_output(); "
        "sys.stdout.write(" + repr(sensitive) + "); sys.stdout.flush(); "
        "sys.stderr.write(" + repr(sensitive) + "); sys.stderr.flush(); "
        "os.write(1," + repr(sensitive.encode()) + "); "
        "os.write(2," + repr(sensitive.encode()) + "); "
        "os._exit(0)"
    )

    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).parents[3],
        check=False,
        capture_output=True,
        timeout=5.0,
    )

    assert completed.returncode == 0
    assert sensitive.encode() not in completed.stdout
    assert sensitive.encode() not in completed.stderr


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
    source_path = (
        Path(__file__).parents[3] / "src" / "quantiqmt" / "live" / "qmt" / "readonly_probe.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    trader_calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Attribute)
        and isinstance(node.func.value.value, ast.Name)
        and node.func.value.value.id == "self"
        and node.func.value.attr == "_trader"
    }

    assert trader_calls == {
        "start",
        "connect",
        "subscribe",
        "query_account_status",
        "query_stock_asset",
        "query_stock_positions",
        "query_stock_orders",
        "query_stock_trades",
        "unsubscribe",
        "stop",
    }
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"getattr", "setattr"}
        and node.args
        and isinstance(node.args[0], ast.Attribute)
        and isinstance(node.args[0].value, ast.Name)
        and node.args[0].value.id == "self"
        and node.args[0].attr == "_trader"
        for node in ast.walk(tree)
    )
