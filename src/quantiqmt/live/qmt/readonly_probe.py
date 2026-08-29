"""Bounded, fail-closed Mini QMT read-only environment probe.

The vendor package is imported only by the Windows worker and is wrapped by a
facade that has no order or cancellation methods.
"""

from __future__ import annotations

import ctypes
import hashlib
import importlib
import importlib.metadata
import multiprocessing
import os
import platform
import queue
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol, TextIO, cast

READONLY_PROFILE = "MINIQMT_SIM_READONLY"
MIN_TIMEOUT_SECONDS = 1.0
MAX_TIMEOUT_SECONDS = 300.0
SUPPORTED_ACCOUNT_TYPE = "STOCK"
STOCK_ACCOUNT_TYPE_CODE = 2
HEALTHY_ACCOUNT_STATUS_CODE = 0
ERROR_ALREADY_EXISTS = 183

PROFILE_KEY = "QUANTIQMT_PROFILE"
USERDATA_PATH_KEY = "QUANTIQMT_QMT_USERDATA_PATH"
ACCOUNT_ID_KEY = "QUANTIQMT_QMT_ACCOUNT_ID"
ACCOUNT_TYPE_KEY = "QUANTIQMT_QMT_ACCOUNT_TYPE"
SESSION_ID_KEY = "QUANTIQMT_QMT_SESSION_ID"
ACCOUNT_ALLOWLIST_KEY = "QUANTIQMT_QMT_ALLOWED_ACCOUNT_IDS"
SIMULATION_CONFIRMED_KEY = "QUANTIQMT_QMT_SIMULATION_ACCOUNT_CONFIRMED"
TIMEOUT_KEY = "QUANTIQMT_QMT_PROBE_TIMEOUT_SECONDS"
ORDER_SEND_ENABLED_KEY = "QUANTIQMT_QMT_ORDER_SEND_ENABLED"
KILL_SWITCH_KEY = "QUANTIQMT_KILL_SWITCH_ENGAGED"

PROBE_ENV_KEYS = frozenset(
    {
        PROFILE_KEY,
        USERDATA_PATH_KEY,
        ACCOUNT_ID_KEY,
        ACCOUNT_TYPE_KEY,
        SESSION_ID_KEY,
        ACCOUNT_ALLOWLIST_KEY,
        SIMULATION_CONFIRMED_KEY,
        TIMEOUT_KEY,
        ORDER_SEND_ENABLED_KEY,
        KILL_SWITCH_KEY,
    }
)


class ProbeConfigError(ValueError):
    """Configuration failure carrying only a stable, non-sensitive reason code."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True, repr=False)
class ReadonlyProbeConfig:
    """Validated internal probe configuration; account identity is never rendered."""

    userdata_path: Path
    account_id: str
    account_type: str
    session_id: int
    allowed_account_ids: frozenset[str]
    timeout_seconds: float

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> ReadonlyProbeConfig:
        unknown_qmt_keys = {
            key
            for key in environment
            if key.startswith("QUANTIQMT_QMT_") and key not in PROBE_ENV_KEYS
        }
        if unknown_qmt_keys:
            raise ProbeConfigError("CONFIG_UNKNOWN_QMT_KEY")

        if environment.get(PROFILE_KEY, "") != READONLY_PROFILE:
            raise ProbeConfigError("CONFIG_PROFILE_FORBIDDEN")

        account_id = environment.get(ACCOUNT_ID_KEY, "").strip()
        if not account_id:
            raise ProbeConfigError("CONFIG_ACCOUNT_REQUIRED")

        account_type = environment.get(ACCOUNT_TYPE_KEY, "").strip().upper()
        if not account_type:
            raise ProbeConfigError("CONFIG_ACCOUNT_TYPE_REQUIRED")
        if account_type != SUPPORTED_ACCOUNT_TYPE:
            raise ProbeConfigError("CONFIG_ACCOUNT_TYPE_FORBIDDEN")

        allowlist_parts = [
            item.strip() for item in environment.get(ACCOUNT_ALLOWLIST_KEY, "").split(",")
        ]
        if not allowlist_parts or any(not item for item in allowlist_parts):
            raise ProbeConfigError("CONFIG_ACCOUNT_ALLOWLIST_INVALID")
        allowed_account_ids = frozenset(allowlist_parts)
        if len(allowed_account_ids) != len(allowlist_parts):
            raise ProbeConfigError("CONFIG_ACCOUNT_ALLOWLIST_INVALID")
        if account_id not in allowed_account_ids:
            raise ProbeConfigError("CONFIG_ACCOUNT_NOT_ALLOWED")

        if environment.get(SIMULATION_CONFIRMED_KEY, "").strip().lower() != "true":
            raise ProbeConfigError("CONFIG_SIMULATION_CONFIRMATION_REQUIRED")

        if environment.get(ORDER_SEND_ENABLED_KEY, "false").strip().lower() != "false":
            raise ProbeConfigError("CONFIG_ORDER_SEND_FORBIDDEN")
        if environment.get(KILL_SWITCH_KEY, "true").strip().lower() != "true":
            raise ProbeConfigError("CONFIG_KILL_SWITCH_REQUIRED")

        session_id = _positive_int(environment.get(SESSION_ID_KEY, ""), "CONFIG_SESSION_INVALID")
        timeout_seconds = _bounded_timeout(environment.get(TIMEOUT_KEY, ""))

        raw_userdata_path = environment.get(USERDATA_PATH_KEY, "").strip()
        if not raw_userdata_path:
            raise ProbeConfigError("CONFIG_USERDATA_INVALID")
        userdata_path = Path(raw_userdata_path).expanduser()
        if userdata_path.name.lower() != "userdata_mini" or not userdata_path.is_dir():
            raise ProbeConfigError("CONFIG_USERDATA_INVALID")

        return cls(
            userdata_path=userdata_path.resolve(),
            account_id=account_id,
            account_type=account_type,
            session_id=session_id,
            allowed_account_ids=allowed_account_ids,
            timeout_seconds=timeout_seconds,
        )


def _positive_int(raw_value: str, reason_code: str) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ProbeConfigError(reason_code) from exc
    if value <= 0:
        raise ProbeConfigError(reason_code)
    return value


def _bounded_timeout(raw_value: str) -> float:
    try:
        value = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise ProbeConfigError("CONFIG_TIMEOUT_INVALID") from exc
    if not MIN_TIMEOUT_SECONDS <= value <= MAX_TIMEOUT_SECONDS:
        raise ProbeConfigError("CONFIG_TIMEOUT_INVALID")
    return value


@dataclass(frozen=True)
class RuntimeIdentity:
    platform: str
    python_version: str
    xtquant_version: str | None


def detect_runtime_identity() -> RuntimeIdentity:
    """Detect versions without importing the native xtquant extension."""

    try:
        xtquant_version: str | None = importlib.metadata.version("xtquant")
    except importlib.metadata.PackageNotFoundError:
        xtquant_version = None
    return RuntimeIdentity(
        platform=platform.system(),
        python_version=platform.python_version(),
        xtquant_version=xtquant_version,
    )


@dataclass(frozen=True)
class ProbeReport:
    """Public evidence containing no account identity or vendor query objects."""

    passed: bool
    reason_code: str
    platform: str
    python_version: str
    xtquant_version: str | None
    userdata_leaf: str
    connected: bool = False
    subscribed: bool = False
    account_status_queried: bool = False
    asset_queried: bool = False
    positions_queried: bool = False
    orders_queried: bool = False
    trades_queried: bool = False
    positions_count: int | None = None
    orders_count: int | None = None
    trades_count: int | None = None

    def to_public_dict(self) -> dict[str, object]:
        return cast(dict[str, object], asdict(self))


def failure_report(
    reason_code: str,
    *,
    runtime: RuntimeIdentity | None = None,
    userdata_leaf: str = "unverified",
    connected: bool = False,
    subscribed: bool = False,
    account_status_queried: bool = False,
    asset_queried: bool = False,
    positions_queried: bool = False,
    orders_queried: bool = False,
    trades_queried: bool = False,
) -> ProbeReport:
    identity = runtime or detect_runtime_identity()
    return ProbeReport(
        passed=False,
        reason_code=reason_code,
        platform=identity.platform,
        python_version=identity.python_version,
        xtquant_version=identity.xtquant_version,
        userdata_leaf=userdata_leaf,
        connected=connected,
        subscribed=subscribed,
        account_status_queried=account_status_queried,
        asset_queried=asset_queried,
        positions_queried=positions_queried,
        orders_queried=orders_queried,
        trades_queried=trades_queried,
    )


class ReadonlyVendorFacade(Protocol):
    """Only the vendor operations authorized by TASK-055."""

    def start(self) -> None: ...

    def connect(self) -> int: ...

    def subscribe(self) -> int: ...

    def query_account_status(self) -> Sequence[VendorAccountStatus] | None: ...

    def query_asset(self) -> object | None: ...

    def query_positions(self) -> Sequence[object] | None: ...

    def query_orders(self) -> Sequence[object] | None: ...

    def query_trades(self) -> Sequence[object] | None: ...

    def unsubscribe(self) -> None: ...

    def stop(self) -> None: ...


@dataclass(frozen=True, repr=False)
class VendorAccountStatus:
    account_id: str
    account_type: int
    status: int


class _XtQuantReadonlyFacade:
    """Narrow wrapper deliberately excluding every trading side-effect method."""

    def __init__(self, trader: Any, account: Any) -> None:
        self._trader = trader
        self._account = account

    def start(self) -> None:
        self._trader.start()

    def connect(self) -> int:
        return int(self._trader.connect())

    def subscribe(self) -> int:
        return int(self._trader.subscribe(self._account))

    def query_account_status(self) -> Sequence[VendorAccountStatus] | None:
        raw_statuses = self._trader.query_account_status()
        if raw_statuses is None:
            return None
        return [
            VendorAccountStatus(
                account_id=str(raw_status.account_id),
                account_type=int(raw_status.account_type),
                status=int(raw_status.status),
            )
            for raw_status in raw_statuses
        ]

    def query_asset(self) -> object | None:
        return cast(object | None, self._trader.query_stock_asset(self._account))

    def query_positions(self) -> Sequence[object] | None:
        return cast(Sequence[object] | None, self._trader.query_stock_positions(self._account))

    def query_orders(self) -> Sequence[object] | None:
        return cast(Sequence[object] | None, self._trader.query_stock_orders(self._account))

    def query_trades(self) -> Sequence[object] | None:
        return cast(Sequence[object] | None, self._trader.query_stock_trades(self._account))

    def unsubscribe(self) -> None:
        self._trader.unsubscribe(self._account)

    def stop(self) -> None:
        self._trader.stop()


def _create_xtquant_readonly_facade(config: ReadonlyProbeConfig) -> ReadonlyVendorFacade:
    """Import and construct the native vendor client inside the isolated worker."""

    trader_module = importlib.import_module("xtquant.xttrader")
    type_module = importlib.import_module("xtquant.xttype")
    trader_type = trader_module.XtQuantTrader
    account_type = type_module.StockAccount
    trader = trader_type(str(config.userdata_path), config.session_id)
    account = account_type(config.account_id, config.account_type)
    return _XtQuantReadonlyFacade(trader, account)


class _ProbeFailure(Exception):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def run_probe(
    config: ReadonlyProbeConfig,
    facade_factory: Callable[[ReadonlyProbeConfig], ReadonlyVendorFacade],
    *,
    runtime: RuntimeIdentity | None = None,
) -> ProbeReport:
    """Run the read-only calls; caller provides the subprocess deadline boundary."""

    identity = runtime or detect_runtime_identity()
    userdata_leaf = config.userdata_path.name
    if identity.platform != "Windows":
        return failure_report(
            "RUNTIME_WINDOWS_REQUIRED", runtime=identity, userdata_leaf=userdata_leaf
        )
    if identity.xtquant_version is None:
        return failure_report(
            "RUNTIME_XTQUANT_UNAVAILABLE", runtime=identity, userdata_leaf=userdata_leaf
        )

    started = False
    connected = False
    subscribed = False
    status_queried = False
    asset_queried = False
    positions_queried = False
    orders_queried = False
    trades_queried = False
    positions_count: int | None = None
    orders_count: int | None = None
    trades_count: int | None = None
    failure_code: str | None = None
    facade: ReadonlyVendorFacade | None = None

    try:
        try:
            facade = facade_factory(config)
        except Exception as exc:
            raise _ProbeFailure("RUNTIME_XTQUANT_IMPORT_FAILED") from exc

        try:
            facade.start()
            started = True
        except Exception as exc:
            raise _ProbeFailure("CLIENT_START_FAILED") from exc

        try:
            if facade.connect() != 0:
                raise _ProbeFailure("CLIENT_CONNECT_FAILED")
            connected = True
        except _ProbeFailure:
            raise
        except Exception as exc:
            raise _ProbeFailure("CLIENT_CONNECT_FAILED") from exc

        try:
            if facade.subscribe() != 0:
                raise _ProbeFailure("ACCOUNT_SUBSCRIBE_FAILED")
            subscribed = True
        except _ProbeFailure:
            raise
        except Exception as exc:
            raise _ProbeFailure("ACCOUNT_SUBSCRIBE_FAILED") from exc

        try:
            statuses = facade.query_account_status()
            if statuses is None:
                raise _ProbeFailure("QUERY_ACCOUNT_STATUS_FAILED")
            status_queried = True
            if len(statuses) != 1:
                raise _ProbeFailure("QUERY_ACCOUNT_IDENTITY_AMBIGUOUS")
            status = statuses[0]
            if status.account_id != config.account_id:
                raise _ProbeFailure("QUERY_ACCOUNT_IDENTITY_MISMATCH")
            if status.account_type != STOCK_ACCOUNT_TYPE_CODE:
                raise _ProbeFailure("QUERY_ACCOUNT_TYPE_MISMATCH")
            if status.status != HEALTHY_ACCOUNT_STATUS_CODE:
                raise _ProbeFailure("QUERY_ACCOUNT_STATUS_UNHEALTHY")
        except _ProbeFailure:
            raise
        except Exception as exc:
            raise _ProbeFailure("QUERY_ACCOUNT_STATUS_FAILED") from exc

        try:
            if facade.query_asset() is None:
                raise _ProbeFailure("QUERY_ASSET_FAILED")
            asset_queried = True
        except _ProbeFailure:
            raise
        except Exception as exc:
            raise _ProbeFailure("QUERY_ASSET_FAILED") from exc

        positions = _required_sequence(facade.query_positions(), "QUERY_POSITIONS_FAILED")
        positions_queried = True
        positions_count = len(positions)
        orders = _required_sequence(facade.query_orders(), "QUERY_ORDERS_FAILED")
        orders_queried = True
        orders_count = len(orders)
        trades = _required_sequence(facade.query_trades(), "QUERY_TRADES_FAILED")
        trades_queried = True
        trades_count = len(trades)
    except _ProbeFailure as exc:
        failure_code = exc.reason_code
    except Exception:
        failure_code = _query_stage_failure(
            positions_queried=positions_queried,
            orders_queried=orders_queried,
            trades_queried=trades_queried,
        )
    finally:
        cleanup_failed = False
        if facade is not None and subscribed:
            try:
                facade.unsubscribe()
            except Exception:
                cleanup_failed = True
        if facade is not None and started:
            try:
                facade.stop()
            except Exception:
                cleanup_failed = True
        if cleanup_failed and failure_code is None:
            failure_code = "CLIENT_CLEANUP_FAILED"

    if failure_code is not None:
        return failure_report(
            failure_code,
            runtime=identity,
            userdata_leaf=userdata_leaf,
            connected=connected,
            subscribed=subscribed,
            account_status_queried=status_queried,
            asset_queried=asset_queried,
            positions_queried=positions_queried,
            orders_queried=orders_queried,
            trades_queried=trades_queried,
        )

    return ProbeReport(
        passed=True,
        reason_code="PROBE_OK",
        platform=identity.platform,
        python_version=identity.python_version,
        xtquant_version=identity.xtquant_version,
        userdata_leaf=userdata_leaf,
        connected=connected,
        subscribed=subscribed,
        account_status_queried=status_queried,
        asset_queried=asset_queried,
        positions_queried=positions_queried,
        orders_queried=orders_queried,
        trades_queried=trades_queried,
        positions_count=positions_count,
        orders_count=orders_count,
        trades_count=trades_count,
    )


def _required_sequence(value: Sequence[object] | None, reason_code: str) -> Sequence[object]:
    if value is None or isinstance(value, str | bytes):
        raise _ProbeFailure(reason_code)
    return value


def _query_stage_failure(
    *, positions_queried: bool, orders_queried: bool, trades_queried: bool
) -> str:
    if not positions_queried:
        return "QUERY_POSITIONS_FAILED"
    if not orders_queried:
        return "QUERY_ORDERS_FAILED"
    if not trades_queried:
        return "QUERY_TRADES_FAILED"
    return "PROBE_INTERNAL_FAILED"


def _isolate_worker_output() -> TextIO:
    """Redirect Python and native fd 1/2 output before importing the vendor package."""

    sink = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115 - owned until worker exit
    try:
        os.dup2(sink.fileno(), 1)
        os.dup2(sink.fileno(), 2)
        sys.stdout = sink
        sys.stderr = sink
    except BaseException:
        sink.close()
        raise
    return sink


def _probe_worker(config: ReadonlyProbeConfig, output_queue: Any) -> None:
    try:
        sink = _isolate_worker_output()
    except BaseException:
        output_queue.put(
            failure_report("PROBE_OUTPUT_ISOLATION_FAILED", userdata_leaf=config.userdata_path.name)
        )
        return
    try:
        try:
            report = run_probe(config, _create_xtquant_readonly_facade)
        except BaseException:
            report = failure_report("PROBE_WORKER_FAILED", userdata_leaf=config.userdata_path.name)
        output_queue.put(report)
    finally:
        # The worker process owns this descriptor until exit; closing it early would leave
        # sys.stdout/sys.stderr referencing a closed stream during interpreter shutdown.
        _ = sink


def _gated_probe_worker(config: ReadonlyProbeConfig, output_queue: Any, launch_gate: Any) -> None:
    if not launch_gate.wait(config.timeout_seconds):
        return
    _probe_worker(config, output_queue)


class SessionMutexError(RuntimeError):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


class _SessionMutex(Protocol):
    def release(self) -> None: ...


class _NoopSessionMutex:
    def release(self) -> None:
        return


class _WindowsSessionMutex:
    def __init__(self, kernel32: Any, handle: int) -> None:
        self._kernel32 = kernel32
        self._handle = handle

    def release(self) -> None:
        if self._handle == 0:
            return
        handle = self._handle
        self._handle = 0
        if not self._kernel32.CloseHandle(handle):
            raise SessionMutexError("PROBE_SESSION_LOCK_RELEASE_FAILED")


def _acquire_session_mutex(config: ReadonlyProbeConfig) -> _SessionMutex:
    if platform.system() != "Windows":
        return _NoopSessionMutex()

    identity = f"{str(config.userdata_path).casefold()}\0{config.session_id}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    mutex_name = f"Local\\QuantiQmt.ReadonlyProbe.{digest}"
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_mutex = kernel32.CreateMutexW
        create_mutex.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        create_mutex.restype = ctypes.c_void_p
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [ctypes.c_void_p]
        close_handle.restype = ctypes.c_int
        handle_value = create_mutex(None, 0, mutex_name)
        error_code = ctypes.get_last_error()
    except Exception as exc:
        raise SessionMutexError("PROBE_SESSION_LOCK_FAILED") from exc

    if not handle_value:
        raise SessionMutexError("PROBE_SESSION_LOCK_FAILED")
    handle = int(handle_value)
    if error_code == ERROR_ALREADY_EXISTS:
        close_handle(handle)
        raise SessionMutexError("PROBE_SESSION_IN_USE")
    return _WindowsSessionMutex(kernel32, handle)


def run_probe_isolated(
    config: ReadonlyProbeConfig,
    *,
    context: Any | None = None,
) -> ProbeReport:
    """Run in a spawned process and forcibly terminate it at the configured deadline."""

    deadline = time.monotonic() + config.timeout_seconds
    try:
        session_mutex = _acquire_session_mutex(config)
    except SessionMutexError as exc:
        return failure_report(exc.reason_code, userdata_leaf=config.userdata_path.name)

    try:
        report = _run_probe_isolated_locked(config, deadline=deadline, context=context)
    finally:
        try:
            session_mutex.release()
        except SessionMutexError:
            report = failure_report(
                "PROBE_SESSION_LOCK_RELEASE_FAILED", userdata_leaf=config.userdata_path.name
            )
    return report


def _run_probe_isolated_locked(
    config: ReadonlyProbeConfig, *, deadline: float, context: Any | None
) -> ProbeReport:
    process_context = context or multiprocessing.get_context("spawn")
    process: Any | None = None
    output_queue: Any | None = None
    try:
        output_queue = process_context.Queue()
        launch_gate = process_context.Event()
        process = process_context.Process(
            target=_gated_probe_worker, args=(config, output_queue, launch_gate)
        )
    except Exception:
        stopped = _force_stop_process(process)
        reason_code = "PROBE_WORKER_START_FAILED" if stopped else "PROBE_TERMINATION_FAILED"
        return _finalize_process_report(
            failure_report(reason_code, userdata_leaf=config.userdata_path.name),
            process,
            output_queue,
        )

    if process is None:
        return _finalize_process_report(
            failure_report("PROBE_WORKER_START_FAILED", userdata_leaf=config.userdata_path.name),
            process,
            output_queue,
        )

    start_status = _start_process_with_deadline(
        process, launch_gate, deadline=deadline, output_queue=output_queue
    )
    if start_status == "timeout":
        return failure_report("PROBE_DEADLINE_EXCEEDED", userdata_leaf=config.userdata_path.name)
    if start_status == "failed":
        stopped = _force_stop_process(process)
        reason_code = "PROBE_WORKER_START_FAILED" if stopped else "PROBE_TERMINATION_FAILED"
        return _finalize_process_report(
            failure_report(reason_code, userdata_leaf=config.userdata_path.name),
            process,
            output_queue,
        )

    try:
        remaining = deadline - time.monotonic()
        if remaining > 0:
            process.join(remaining)
        if process.is_alive():
            stopped = _force_stop_process(process)
            reason_code = "PROBE_DEADLINE_EXCEEDED" if stopped else "PROBE_TERMINATION_FAILED"
            return _finalize_process_report(
                failure_report(reason_code, userdata_leaf=config.userdata_path.name),
                process,
                output_queue,
            )

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return _finalize_process_report(
                failure_report("PROBE_DEADLINE_EXCEEDED", userdata_leaf=config.userdata_path.name),
                process,
                output_queue,
            )
        try:
            result = output_queue.get(timeout=remaining)
        except (queue.Empty, LookupError):
            return _finalize_process_report(
                failure_report("PROBE_WORKER_NO_RESULT", userdata_leaf=config.userdata_path.name),
                process,
                output_queue,
            )
        if not isinstance(result, ProbeReport):
            return _finalize_process_report(
                failure_report(
                    "PROBE_WORKER_INVALID_RESULT", userdata_leaf=config.userdata_path.name
                ),
                process,
                output_queue,
            )
        return _finalize_process_report(result, process, output_queue)
    except Exception:
        stopped = _force_stop_process(process)
        reason_code = "PROBE_PROCESS_CONTROL_FAILED" if stopped else "PROBE_TERMINATION_FAILED"
        return _finalize_process_report(
            failure_report(reason_code, userdata_leaf=config.userdata_path.name),
            process,
            output_queue,
        )


def _start_process_with_deadline(
    process: Any, launch_gate: Any, *, deadline: float, output_queue: Any
) -> str:
    start_done = threading.Event()
    decision = threading.Event()
    state = {"allowed": False, "failed": False, "timed_out": False}

    def launch() -> None:
        try:
            process.start()
        except BaseException:
            state["failed"] = True
        finally:
            start_done.set()
        decision.wait()
        if state["allowed"]:
            launch_gate.set()
        elif state["timed_out"]:
            _force_stop_process(process)
            _close_process_resources(process, output_queue)

    launch_thread = threading.Thread(target=launch, daemon=True, name="qmt-probe-launch")
    launch_thread.start()
    remaining = max(0.0, deadline - time.monotonic())
    if not start_done.wait(remaining):
        state["timed_out"] = True
        decision.set()
        return "timeout"
    if state["failed"]:
        decision.set()
        launch_thread.join(0.1)
        return "failed"
    if time.monotonic() >= deadline:
        state["timed_out"] = True
        decision.set()
        return "timeout"
    state["allowed"] = True
    decision.set()
    launch_thread.join(0.1)
    return "started"


def _force_stop_process(process: Any | None) -> bool:
    if process is None:
        return True
    try:
        if not process.is_alive():
            return True
    except Exception:
        return False
    with suppress(Exception):
        process.terminate()
    with suppress(Exception):
        process.join(1.0)
    try:
        if not process.is_alive():
            return True
    except Exception:
        return False
    try:
        process.kill()
    except Exception:
        return False
    try:
        process.join(1.0)
        return not bool(process.is_alive())
    except Exception:
        return False


def _finalize_process_report(
    report: ProbeReport, process: Any | None, output_queue: Any | None
) -> ProbeReport:
    cleanup_succeeded = _close_process_resources(process, output_queue)
    if report.passed and not cleanup_succeeded:
        return failure_report(
            "PROBE_RESOURCE_CLEANUP_FAILED",
            userdata_leaf=report.userdata_leaf,
            runtime=RuntimeIdentity(
                platform=report.platform,
                python_version=report.python_version,
                xtquant_version=report.xtquant_version,
            ),
            connected=report.connected,
            subscribed=report.subscribed,
            account_status_queried=report.account_status_queried,
            asset_queried=report.asset_queried,
            positions_queried=report.positions_queried,
            orders_queried=report.orders_queried,
            trades_queried=report.trades_queried,
        )
    return report


def _close_process_resources(process: Any | None, output_queue: Any | None) -> bool:
    cleanup_succeeded = True
    if output_queue is not None:
        try:
            output_queue.cancel_join_thread()
        except Exception:
            cleanup_succeeded = False
        try:
            output_queue.close()
        except Exception:
            cleanup_succeeded = False
    if process is not None:
        try:
            if process.is_alive():
                cleanup_succeeded = False
            else:
                process.close()
        except Exception:
            cleanup_succeeded = False
    return cleanup_succeeded


def load_probe_environment(
    env_file: Path, process_environment: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Load literal allowlisted values without interpolation or process-env override."""

    environment = dict(process_environment if process_environment is not None else os.environ)
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ProbeConfigError("ENV_FILE_UNREADABLE") from exc

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ProbeConfigError("ENV_LINE_INVALID")
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if _is_secret_key(key) or (key.startswith("QUANTIQMT_QMT_") and key not in PROBE_ENV_KEYS):
            raise ProbeConfigError("ENV_KEY_FORBIDDEN")
        if key not in PROBE_ENV_KEYS:
            continue
        value = _unquote_literal(raw_value.strip())
        environment.setdefault(key, value)
    return environment


def _is_secret_key(key: str) -> bool:
    normalized = key.upper()
    return any(fragment in normalized for fragment in ("PASSWORD", "SECRET", "TOKEN"))


def _unquote_literal(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def default_exit_code(report: ProbeReport) -> int:
    return 0 if report.passed else 2


if __name__ == "__main__":  # pragma: no cover - use the dedicated script entry point
    sys.exit(2)
