"""Pure OMS Order aggregate governed by ``SM-ORDER``.

The aggregate accepts already-validated domain evidence.  It never queries a
clock, broker, database, or cache and it never treats an uncertain result as a
reason to retry an external operation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from quantiqmt.shared import Identifier, Quantity


class OrderState(StrEnum):
    REGISTERED = "REGISTERED"
    RISK_PENDING = "RISK_PENDING"
    APPROVED = "APPROVED"
    SUBMITTING = "SUBMITTING"
    SUBMIT_UNKNOWN = "SUBMIT_UNKNOWN"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCEL_UNKNOWN = "CANCEL_UNKNOWN"
    SUSPENDED = "SUSPENDED"
    REJECTED = "REJECTED"
    CANCELED = "CANCELED"
    FILLED = "FILLED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


class OrderEvent(StrEnum):
    START_RISK = "StartRisk"
    RISK_PASSED = "RiskPassed"
    RISK_REJECTED = "RiskRejected"
    DISPATCH = "Dispatch"
    BROKER_ACCEPTED = "BrokerAccepted"
    BROKER_REJECTED = "BrokerRejected"
    BROKER_EXPIRED = "BrokerExpired"
    OUTCOME_UNKNOWN = "OutcomeUnknown"
    RECONCILE_FOUND_ACTIVE = "ReconcileFoundActive"
    RECONCILE_FOUND_PARTIAL = "ReconcileFoundPartial"
    RECONCILE_FOUND_REJECTED = "ReconcileFoundRejected"
    RECONCILE_FOUND_CANCELED = "ReconcileFoundCanceled"
    RECONCILE_FOUND_EXPIRED = "ReconcileFoundExpired"
    RECONCILE_CANCEL_REJECTED_ACTIVE = "ReconcileCancelRejectedActive"
    RECONCILE_CANCEL_REJECTED_PARTIAL = "ReconcileCancelRejectedPartial"
    RECONCILE_CONFIRMED_ABSENT = "ReconcileConfirmedAbsent"
    RECONCILE_CANCELED = "ReconcileCanceled"
    RECONCILE_AMBIGUOUS = "ReconcileAmbiguous"
    PARTIAL_TRADE = "PartialTrade"
    FULL_TRADE = "FullTrade"
    REQUEST_CANCEL = "RequestCancel"
    CANCEL_CONFIRMED = "CancelConfirmed"
    FACT_CONFLICT = "FactConflict"
    REPORT_CUMULATIVE_MISMATCH = "ReportCumulativeMismatch"
    REPORT_CORRELATION_AMBIGUOUS = "ReportCorrelationAmbiguous"


class OrderAction(StrEnum):
    REQUEST_RISK_EVALUATION = "RequestRiskEvaluation"
    PERSIST_ORDER_APPROVED = "PersistOrderApproved"
    PERSIST_ORDER_REJECTED = "PersistOrderRejected"
    START_EXECUTION_ATTEMPT = "StartExecutionAttempt"
    MERGE_BROKER_REPORT = "MergeBrokerReport"
    SCHEDULE_RECONCILIATION = "ScheduleReconciliation"
    IMPORT_BROKER_FACTS = "ImportBrokerFacts"
    PERSIST_SUBMIT_FAILED = "PersistSubmitFailed"
    OPEN_RECONCILIATION_CASE = "OpenReconciliationCase"
    RECORD_TRADE = "RecordTrade"
    RECORD_TRADE_AND_OPEN_DIFFERENCE_CASE = "RecordTradeAndOpenDifferenceCase"
    START_CANCEL_ATTEMPT = "StartCancelAttempt"


class OrderDomainError(ValueError):
    """Base error carrying a stable catalog code."""

    code: str

    def __init__(self, message: str) -> None:
        super().__init__(f"{self.code}: {message}")


class InvalidOrderTransition(OrderDomainError):
    code = "QQ-OMS-5002"


class OrderVersionConflict(OrderDomainError):
    code = "QQ-COMMON-1003"


class RiskSnapshotUnavailable(OrderDomainError):
    code = "QQ-RISK-4002"


@dataclass(frozen=True, slots=True)
class FactIdentity:
    """Stable namespaced identity of one authoritative external fact."""

    namespace: str
    key: str

    def __post_init__(self) -> None:
        if not self.namespace.strip() or not self.key.strip():
            raise ValueError("fact identity namespace and key must be non-empty")


@dataclass(frozen=True, slots=True)
class ExternalFact:
    """Canonical identity/fingerprint plus optional single-trade quantity."""

    identity: FactIdentity
    fingerprint: str
    trade_quantity: Quantity | None = None
    broker_sequence: int | None = None
    stream: str | None = None

    def __post_init__(self) -> None:
        if not self.fingerprint.strip():
            raise ValueError("canonical fingerprint must be non-empty")
        if self.trade_quantity is not None:
            self.trade_quantity.require_positive()
        if self.broker_sequence is not None and self.broker_sequence < 0:
            raise ValueError("broker sequence cannot be negative")
        if self.broker_sequence is not None and not self.stream:
            raise ValueError("broker sequence requires a stream")


@dataclass(frozen=True, slots=True)
class GuardEvidence:
    """Facts used to evaluate guards; no field defaults to successful."""

    externally_proven: frozenset[str] = frozenset()
    snapshot_ids: tuple[str, str, str] | None = None
    snapshots_usable: bool = False
    expected_order_version: int | None = None
    is_leader: bool = False
    fencing_token_valid: bool = False
    system_trading_allowed: bool = False
    account_trading_allowed: bool = False

    @classmethod
    def of(cls, *guards: str) -> GuardEvidence:
        """Supply externally established Broker/reconciliation evidence."""

        return cls(externally_proven=frozenset(guards))

    @classmethod
    def risk_snapshots(cls, account: str, portfolio: str, market: str) -> GuardEvidence:
        return cls(snapshot_ids=(account, portfolio, market), snapshots_usable=True)

    @classmethod
    def expected_version(cls, version: int) -> GuardEvidence:
        return cls(expected_order_version=version)

    @classmethod
    def trading_authority(cls) -> GuardEvidence:
        return cls(
            is_leader=True,
            fencing_token_valid=True,
            system_trading_allowed=True,
            account_trading_allowed=True,
        )


@dataclass(frozen=True, slots=True)
class TransitionResult:
    previous: OrderState
    current: OrderState
    event: OrderEvent
    action: OrderAction
    version: int


@dataclass(frozen=True, slots=True)
class _Definition:
    target: OrderState
    guard: str
    action: OrderAction


# Compact, immutable transcription of every transition in SM-ORDER 0.3.
_ROWS = """
REGISTERED|StartRisk|RISK_PENDING|snapshots_available|RequestRiskEvaluation
RISK_PENDING|RiskPassed|APPROVED|expected_version_matches|PersistOrderApproved
RISK_PENDING|RiskRejected|REJECTED|expected_version_matches|PersistOrderRejected
APPROVED|Dispatch|SUBMITTING|leader_and_trading_allowed|StartExecutionAttempt
SUBMITTING|BrokerAccepted|SUBMITTED|report_uniquely_correlated|MergeBrokerReport
SUBMITTING|BrokerRejected|REJECTED|outcome_definite|MergeBrokerReport
SUBMITTING|OutcomeUnknown|SUBMIT_UNKNOWN|true|ScheduleReconciliation
SUBMIT_UNKNOWN|ReconcileFoundActive|SUBMITTED|unique_broker_match|ImportBrokerFacts
SUBMIT_UNKNOWN|ReconcileFoundRejected|REJECTED|unique_broker_match_and_definite_rejection|ImportBrokerFacts
SUBMIT_UNKNOWN|ReconcileFoundCanceled|CANCELED|unique_broker_match_and_definite_canceled|ImportBrokerFacts
SUBMIT_UNKNOWN|ReconcileFoundExpired|EXPIRED|unique_broker_match_and_definite_expired|ImportBrokerFacts
SUBMIT_UNKNOWN|PartialTrade|PARTIALLY_FILLED|cum_strictly_increases_below_quantity|RecordTrade
SUBMIT_UNKNOWN|FullTrade|FILLED|cum_equals_quantity|RecordTrade
SUBMIT_UNKNOWN|ReconcileConfirmedAbsent|FAILED|visibility_window_passed|PersistSubmitFailed
SUBMIT_UNKNOWN|ReconcileAmbiguous|SUSPENDED|true|OpenReconciliationCase
SUBMITTED|PartialTrade|PARTIALLY_FILLED|cum_between_zero_and_quantity|RecordTrade
PARTIALLY_FILLED|PartialTrade|PARTIALLY_FILLED|cum_strictly_increases_below_quantity|RecordTrade
SUBMITTED|FullTrade|FILLED|cum_equals_quantity|RecordTrade
PARTIALLY_FILLED|FullTrade|FILLED|cum_equals_quantity|RecordTrade
SUBMITTED|BrokerExpired|EXPIRED|broker_confirms_expired|MergeBrokerReport
PARTIALLY_FILLED|BrokerExpired|EXPIRED|broker_confirms_expired_and_leaves_positive|MergeBrokerReport
SUBMITTED|RequestCancel|CANCEL_PENDING|order_not_terminal|StartCancelAttempt
PARTIALLY_FILLED|RequestCancel|CANCEL_PENDING|leaves_positive|StartCancelAttempt
CANCEL_PENDING|CancelConfirmed|CANCELED|broker_confirms_canceled|MergeBrokerReport
CANCEL_PENDING|PartialTrade|CANCEL_PENDING|cum_strictly_increases_below_quantity|RecordTrade
CANCEL_PENDING|OutcomeUnknown|CANCEL_UNKNOWN|true|ScheduleReconciliation
CANCEL_PENDING|FullTrade|FILLED|cum_equals_quantity|RecordTrade
CANCEL_PENDING|BrokerExpired|EXPIRED|broker_confirms_expired_and_leaves_positive|MergeBrokerReport
CANCEL_UNKNOWN|ReconcileFoundActive|SUBMITTED|unique_broker_match_and_cum_zero|ImportBrokerFacts
CANCEL_UNKNOWN|ReconcileFoundPartial|PARTIALLY_FILLED|unique_broker_match_and_cum_between_zero_and_quantity|ImportBrokerFacts
CANCEL_UNKNOWN|ReconcileFoundExpired|EXPIRED|unique_broker_match_and_definite_expired|ImportBrokerFacts
CANCEL_UNKNOWN|ReconcileCancelRejectedActive|SUBMITTED|cancel_rejected_and_trade_derived_cum_zero|ImportBrokerFacts
CANCEL_UNKNOWN|ReconcileCancelRejectedPartial|PARTIALLY_FILLED|cancel_rejected_and_trade_derived_cum_between_zero_and_quantity|ImportBrokerFacts
CANCEL_UNKNOWN|ReconcileFoundRejected|SUSPENDED|original_order_rejected_after_cancel_history|OpenReconciliationCase
CANCEL_UNKNOWN|ReconcileCanceled|CANCELED|broker_confirms_canceled|ImportBrokerFacts
CANCEL_UNKNOWN|PartialTrade|CANCEL_UNKNOWN|cum_strictly_increases_below_quantity|RecordTrade
CANCEL_UNKNOWN|FullTrade|FILLED|cum_equals_quantity|RecordTrade
CANCEL_UNKNOWN|ReconcileAmbiguous|SUSPENDED|true|OpenReconciliationCase
CANCELED|PartialTrade|PARTIALLY_FILLED|late_trade_strictly_increases_below_quantity|RecordTradeAndOpenDifferenceCase
CANCELED|FullTrade|FILLED|late_trade_completes_quantity|RecordTradeAndOpenDifferenceCase
EXPIRED|PartialTrade|PARTIALLY_FILLED|late_trade_strictly_increases_below_quantity|RecordTradeAndOpenDifferenceCase
EXPIRED|FullTrade|FILLED|late_trade_completes_quantity|RecordTradeAndOpenDifferenceCase
REJECTED|PartialTrade|PARTIALLY_FILLED|late_trade_strictly_increases_below_quantity|RecordTradeAndOpenDifferenceCase
REJECTED|FullTrade|FILLED|late_trade_completes_quantity|RecordTradeAndOpenDifferenceCase
FAILED|PartialTrade|PARTIALLY_FILLED|late_trade_strictly_increases_below_quantity|RecordTradeAndOpenDifferenceCase
FAILED|FullTrade|FILLED|late_trade_completes_quantity|RecordTradeAndOpenDifferenceCase
"""


def _base_transitions() -> dict[tuple[OrderState, OrderEvent], _Definition]:
    result: dict[tuple[OrderState, OrderEvent], _Definition] = {}
    for row in _ROWS.strip().splitlines():
        source, event, target, guard, action = row.split("|")
        result[(OrderState(source), OrderEvent(event))] = _Definition(
            OrderState(target), guard, OrderAction(action)
        )
    conflict_states = set(OrderState) - {OrderState.SUSPENDED}
    for state in conflict_states:
        result[(state, OrderEvent.FACT_CONFLICT)] = _Definition(
            OrderState.SUSPENDED,
            "conflicting_same_identity",
            OrderAction.OPEN_RECONCILIATION_CASE,
        )
    report_states = {
        OrderState.SUBMITTING,
        OrderState.SUBMIT_UNKNOWN,
        OrderState.SUBMITTED,
        OrderState.PARTIALLY_FILLED,
        OrderState.CANCEL_PENDING,
        OrderState.CANCEL_UNKNOWN,
        OrderState.CANCELED,
        OrderState.EXPIRED,
        OrderState.REJECTED,
        OrderState.FILLED,
    }
    for state in report_states:
        result[(state, OrderEvent.REPORT_CUMULATIVE_MISMATCH)] = _Definition(
            OrderState.SUSPENDED,
            "report_cumulative_mismatch",
            OrderAction.OPEN_RECONCILIATION_CASE,
        )
        result[(state, OrderEvent.REPORT_CORRELATION_AMBIGUOUS)] = _Definition(
            OrderState.SUSPENDED,
            "report_correlation_ambiguous",
            OrderAction.OPEN_RECONCILIATION_CASE,
        )
    return result


_TRANSITIONS = MappingProxyType(_base_transitions())
_TRADE_EVENTS = frozenset({OrderEvent.PARTIAL_TRADE, OrderEvent.FULL_TRADE})
_FACT_EVENTS = frozenset(
    {
        OrderEvent.BROKER_ACCEPTED,
        OrderEvent.BROKER_REJECTED,
        OrderEvent.BROKER_EXPIRED,
        OrderEvent.CANCEL_CONFIRMED,
        OrderEvent.PARTIAL_TRADE,
        OrderEvent.FULL_TRADE,
        OrderEvent.FACT_CONFLICT,
        OrderEvent.REPORT_CUMULATIVE_MISMATCH,
        OrderEvent.REPORT_CORRELATION_AMBIGUOUS,
        OrderEvent.RECONCILE_FOUND_ACTIVE,
        OrderEvent.RECONCILE_FOUND_PARTIAL,
        OrderEvent.RECONCILE_FOUND_REJECTED,
        OrderEvent.RECONCILE_FOUND_CANCELED,
        OrderEvent.RECONCILE_FOUND_EXPIRED,
        OrderEvent.RECONCILE_CANCEL_REJECTED_ACTIVE,
        OrderEvent.RECONCILE_CANCEL_REJECTED_PARTIAL,
        OrderEvent.RECONCILE_CANCELED,
        OrderEvent.RECONCILE_AMBIGUOUS,
    }
)
_QUANTITY_GUARDS = frozenset(
    {
        "cum_between_zero_and_quantity",
        "cum_strictly_increases_below_quantity",
        "cum_equals_quantity",
        "late_trade_strictly_increases_below_quantity",
        "late_trade_completes_quantity",
    }
)


@dataclass(slots=True)
class Order:
    order_id: Identifier
    quantity: Quantity
    state: OrderState = OrderState.REGISTERED
    cumulative_quantity: Quantity = field(default_factory=lambda: Quantity(0))
    version: int = 1
    processed_facts: Mapping[FactIdentity, str] = field(default_factory=dict, repr=False)
    broker_sequences: Mapping[str, int] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self.quantity.require_positive()
        if self.version < 1:
            raise ValueError("aggregate version must be >= 1")
        if not 0 <= self.cumulative_quantity.value <= self.quantity.value:
            raise ValueError("restored cumulative quantity must be within order quantity")
        facts = dict(self.processed_facts)
        if any(not fingerprint.strip() for fingerprint in facts.values()):
            raise ValueError("restored fact fingerprints must be non-empty")
        sequences = dict(self.broker_sequences)
        if any(not stream or sequence < 0 for stream, sequence in sequences.items()):
            raise ValueError("restored broker sequences are invalid")
        self.processed_facts = MappingProxyType(facts)
        self.broker_sequences = MappingProxyType(sequences)

    def transition(
        self,
        event: OrderEvent,
        evidence: GuardEvidence,
        *,
        fact: ExternalFact | None = None,
    ) -> TransitionResult | None:
        """Apply one event atomically, or return ``None`` for an idempotent no-op."""

        if event in _FACT_EVENTS and fact is None:
            raise InvalidOrderTransition(f"{event} requires authoritative fact identity")
        if event not in _FACT_EVENTS and fact is not None:
            raise InvalidOrderTransition(f"{event} cannot carry an external fact")

        if fact is not None and fact.identity in self.processed_facts:
            if self.processed_facts[fact.identity] == fact.fingerprint:
                return None
            return self._commit(
                OrderEvent.FACT_CONFLICT,
                GuardEvidence.of("conflicting_same_identity"),
                fact=None,
                remember_fact=False,
            )
        if self.state is OrderState.FILLED and event is OrderEvent.CANCEL_CONFIRMED:
            # A fill wins the cancel race; the later cancellation report is stale.
            return None
        if (
            fact is not None
            and fact.trade_quantity is None
            and fact.broker_sequence is not None
            and fact.stream is not None
            and fact.broker_sequence <= self.broker_sequences.get(fact.stream, -1)
        ):
            return None
        return self._commit(event, evidence, fact=fact, remember_fact=fact is not None)

    def _commit(
        self,
        event: OrderEvent,
        evidence: GuardEvidence,
        *,
        fact: ExternalFact | None,
        remember_fact: bool,
    ) -> TransitionResult | None:
        definition = _TRANSITIONS.get((self.state, event))
        if definition is None:
            raise InvalidOrderTransition(f"undeclared transition {self.state} + {event}")
        if not self._guard_passes(definition.guard, evidence):
            self._guard_failure(definition.guard)
            return None

        candidate = self.cumulative_quantity
        if event in _TRADE_EVENTS:
            if fact is None or fact.trade_quantity is None:
                raise InvalidOrderTransition("trade requires a positive single-trade quantity")
            candidate = Quantity(self.cumulative_quantity.value + fact.trade_quantity.value)
            self._validate_trade_guard(definition.guard, candidate)
        elif fact is not None and fact.trade_quantity is not None:
            raise InvalidOrderTransition("non-trade event cannot carry trade quantity")

        previous = self.state
        next_facts = dict(self.processed_facts)
        next_sequences = dict(self.broker_sequences)
        if remember_fact and fact is not None:
            next_facts[fact.identity] = fact.fingerprint
            if fact.broker_sequence is not None and fact.stream is not None:
                next_sequences[fact.stream] = max(
                    fact.broker_sequence, next_sequences.get(fact.stream, 0)
                )

        # No mutation occurs before all transition, guard, and fact checks pass.
        self.state = definition.target
        self.cumulative_quantity = candidate
        self.processed_facts = MappingProxyType(next_facts)
        self.broker_sequences = MappingProxyType(next_sequences)
        self.version += 1
        return TransitionResult(previous, self.state, event, definition.action, self.version)

    def _guard_passes(self, guard: str, evidence: GuardEvidence) -> bool:
        if guard == "true":
            return True
        if guard == "snapshots_available":
            return bool(
                evidence.snapshots_usable
                and evidence.snapshot_ids
                and all(value.strip() for value in evidence.snapshot_ids)
            )
        if guard == "expected_version_matches":
            return evidence.expected_order_version == self.version
        if guard == "leader_and_trading_allowed":
            return all(
                (
                    evidence.is_leader,
                    evidence.fencing_token_valid,
                    evidence.system_trading_allowed,
                    evidence.account_trading_allowed,
                )
            )
        if guard == "order_not_terminal":
            return self.state not in {
                OrderState.REJECTED,
                OrderState.CANCELED,
                OrderState.FILLED,
                OrderState.EXPIRED,
                OrderState.FAILED,
            }
        if guard == "leaves_positive":
            return self.cumulative_quantity.value < self.quantity.value
        if guard in _QUANTITY_GUARDS:
            return True  # evaluated from the unseen Trade below
        return guard in evidence.externally_proven

    def _guard_failure(self, guard: str) -> None:
        if guard == "snapshots_available":
            raise RiskSnapshotUnavailable("required risk snapshots are unavailable")
        if guard == "expected_version_matches":
            raise OrderVersionConflict("expected order version does not match")
        if guard == "visibility_window_passed":
            return None
        raise InvalidOrderTransition(f"guard evidence missing or failed: {guard}")

    def _validate_trade_guard(self, guard: str, candidate: Quantity) -> None:
        if guard not in _QUANTITY_GUARDS:
            raise InvalidOrderTransition(f"trade transition has non-quantity guard: {guard}")
        current = self.cumulative_quantity.value
        value = candidate.value
        total = self.quantity.value
        if value <= current or value > total:
            raise InvalidOrderTransition("trade cumulative quantity is regressive or excessive")
        if (
            guard
            in {
                "cum_between_zero_and_quantity",
                "cum_strictly_increases_below_quantity",
                "late_trade_strictly_increases_below_quantity",
            }
            and not 0 < value < total
        ):
            raise InvalidOrderTransition("partial trade candidate must be below order quantity")
        if guard in {"cum_equals_quantity", "late_trade_completes_quantity"} and value != total:
            raise InvalidOrderTransition("full trade candidate must equal order quantity")


def transition_catalog() -> frozenset[tuple[OrderState, OrderEvent, OrderState]]:
    return frozenset(
        (source, event, definition.target) for (source, event), definition in _TRANSITIONS.items()
    )
