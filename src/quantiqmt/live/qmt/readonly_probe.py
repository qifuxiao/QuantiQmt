"""Bounded, fail-closed Mini QMT read-only environment probe.

The vendor package is imported only by the Windows worker and is wrapped by a
facade that has no order or cancellation methods.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import multiprocessing
import os
import platform
import queue
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol, cast

READONLY_PROFILE = "MINIQMT_SIM_READONLY"
MIN_TIMEOUT_SECONDS = 1.0
MAX_TIMEOUT_SECONDS = 300.0

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

    def query_account_status(self) -> Sequence[object] | None: ...

    def query_asset(self) -> object | None: ...

    def query_positions(self) -> Sequence[object] | None: ...

    def query_orders(self) -> Sequence[object] | None: ...

    def query_trades(self) -> Sequence[object] | None: ...

    def unsubscribe(self) -> None: ...

    def stop(self) -> None: ...


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

    def query_account_status(self) -> Sequence[object] | None:
        return cast(Sequence[object] | None, self._trader.query_account_status())

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


def create_xtquant_readonly_facade(config: ReadonlyProbeConfig) -> ReadonlyVendorFacade:
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
    facade_factory: Callable[[ReadonlyProbeConfig], ReadonlyVendorFacade] = (
        create_xtquant_readonly_facade
    ),
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
            if not any(
                getattr(status, "account_id", None) == config.account_id for status in statuses
            ):
                raise _ProbeFailure("QUERY_ACCOUNT_IDENTITY_MISMATCH")
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
    if value is None or isinstance(value, (str, bytes)):
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


def _probe_worker(config: ReadonlyProbeConfig, output_queue: Any) -> None:
    try:
        report = run_probe(config)
    except BaseException:
        report = failure_report("PROBE_WORKER_FAILED", userdata_leaf=config.userdata_path.name)
    output_queue.put(report)


def run_probe_isolated(
    config: ReadonlyProbeConfig,
    *,
    context: Any | None = None,
) -> ProbeReport:
    """Run in a spawned process and forcibly terminate it at the configured deadline."""

    process_context = context or multiprocessing.get_context("spawn")
    process: Any | None = None
    try:
        output_queue = process_context.Queue()
        process = process_context.Process(target=_probe_worker, args=(config, output_queue))
        process.start()
    except Exception:
        _terminate_process_safely(process)
        return failure_report("PROBE_WORKER_START_FAILED", userdata_leaf=config.userdata_path.name)

    process.join(config.timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(1.0)
        return failure_report("PROBE_DEADLINE_EXCEEDED", userdata_leaf=config.userdata_path.name)
    try:
        result = output_queue.get(timeout=1.0)
    except (queue.Empty, LookupError):
        return failure_report("PROBE_WORKER_NO_RESULT", userdata_leaf=config.userdata_path.name)
    if not isinstance(result, ProbeReport):
        return failure_report(
            "PROBE_WORKER_INVALID_RESULT", userdata_leaf=config.userdata_path.name
        )
    return result


def _terminate_process_safely(process: Any | None) -> None:
    if process is None:
        return
    try:
        if process.is_alive():
            process.terminate()
            process.join(1.0)
    except Exception:
        return


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
