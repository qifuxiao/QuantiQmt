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


class BrokerStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELED = "CANCELED"
    EXPIRED = "EXPIRED"


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
class ProcessedFact:
    """Recovery record sufficient to validate identity and trade-derived cumulative."""

    fingerprint: str
    trade_quantity: Quantity | None = None

    def __post_init__(self) -> None:
        if not self.fingerprint.strip():
            raise ValueError("processed fact fingerprint must be non-empty")
        if self.trade_quantity is not None:
            self.trade_quantity.require_positive()


@dataclass(frozen=True, slots=True)
class BrokerReportEvidence:
    correlation_count: int
    status: BrokerStatus
    reported_cumulative: Quantity
    leaves_quantity: Quantity
    definite: bool = True

    def __post_init__(self) -> None:
        if self.correlation_count < 0:
            raise ValueError("correlation count cannot be negative")


@dataclass(frozen=True, slots=True)
class ReconciliationEvidence:
    match_count: int
    status: BrokerStatus | None = None
    visibility_window_passed: bool = False
    repeated_absence_confirmed: bool = False
    cancel_rejected: bool = False

    def __post_init__(self) -> None:
        if self.match_count < 0:
            raise ValueError("match count cannot be negative")


@dataclass(frozen=True, slots=True)
class GuardEvidence:
    """Facts used to evaluate guards; no field defaults to successful."""

    snapshot_ids: tuple[str, str, str] | None = None
    snapshots_usable: bool = False
    expected_order_version: int | None = None
    is_leader: bool = False
    fencing_token_valid: bool = False
    system_trading_allowed: bool = False
    account_trading_allowed: bool = False
    broker_report: BrokerReportEvidence | None = None
    reconciliation: ReconciliationEvidence | None = None

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
    processed_facts: Mapping[FactIdentity, ProcessedFact] = field(default_factory=dict, repr=False)
    fact_conflicts: Mapping[FactIdentity, frozenset[str]] = field(default_factory=dict, repr=False)
    broker_sequences: Mapping[str, int] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self.quantity.require_positive()
        if self.version < 1:
            raise ValueError("aggregate version must be >= 1")
        if not 0 <= self.cumulative_quantity.value <= self.quantity.value:
            raise ValueError("restored cumulative quantity must be within order quantity")
        facts = dict(self.processed_facts)
        trade_sum = sum(
            item.trade_quantity.value for item in facts.values() if item.trade_quantity is not None
        )
        if trade_sum != self.cumulative_quantity.value:
            raise ValueError("restored cumulative quantity must equal unique trade fact sum")
        self._validate_state_quantity()
        conflicts = {
            identity: frozenset(values) for identity, values in self.fact_conflicts.items()
        }
        if any(not value.strip() for values in conflicts.values() for value in values):
            raise ValueError("restored conflict fingerprints must be non-empty")
        sequences = dict(self.broker_sequences)
        if any(not stream or sequence < 0 for stream, sequence in sequences.items()):
            raise ValueError("restored broker sequences are invalid")
        self.processed_facts = MappingProxyType(facts)
        self.fact_conflicts = MappingProxyType(conflicts)
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
            accepted = self.processed_facts[fact.identity]
            if accepted.fingerprint == fact.fingerprint:
                return None
            if fact.fingerprint in self.fact_conflicts.get(fact.identity, frozenset()):
                return None
            return self._commit(
                OrderEvent.FACT_CONFLICT,
                GuardEvidence(),
                fact=None,
                remember_fact=False,
                conflict=fact,
            )
        if self.state is OrderState.FILLED and event is OrderEvent.CANCEL_CONFIRMED:
            # A fill wins the cancel race; the later cancellation report is stale.
            return None

        report = evidence.broker_report
        reconciliation = evidence.reconciliation
        normal_report_events = {
            OrderEvent.BROKER_ACCEPTED,
            OrderEvent.BROKER_REJECTED,
            OrderEvent.BROKER_EXPIRED,
            OrderEvent.CANCEL_CONFIRMED,
        }
        if event in normal_report_events and report is not None:
            if report.correlation_count > 1 or (
                report.correlation_count == 0
                and reconciliation is not None
                and reconciliation.visibility_window_passed
            ):
                return self._commit(
                    OrderEvent.REPORT_CORRELATION_AMBIGUOUS,
                    evidence,
                    fact=fact,
                    remember_fact=True,
                    conflict=None,
                )
            if (
                report.correlation_count == 1
                and report.reported_cumulative != self.cumulative_quantity
            ):
                return self._commit(
                    OrderEvent.REPORT_CUMULATIVE_MISMATCH,
                    evidence,
                    fact=fact,
                    remember_fact=True,
                    conflict=None,
                )
        reconciliation_events = {
            OrderEvent.RECONCILE_FOUND_ACTIVE,
            OrderEvent.RECONCILE_FOUND_PARTIAL,
            OrderEvent.RECONCILE_FOUND_REJECTED,
            OrderEvent.RECONCILE_FOUND_CANCELED,
            OrderEvent.RECONCILE_FOUND_EXPIRED,
            OrderEvent.RECONCILE_CANCEL_REJECTED_ACTIVE,
            OrderEvent.RECONCILE_CANCEL_REJECTED_PARTIAL,
            OrderEvent.RECONCILE_CANCELED,
        }
        if event in reconciliation_events and reconciliation is not None:
            if reconciliation.match_count > 1:
                return self._commit(
                    OrderEvent.RECONCILE_AMBIGUOUS,
                    evidence,
                    fact=fact,
                    remember_fact=True,
                    conflict=None,
                )
            if reconciliation.match_count == 0 and not reconciliation.visibility_window_passed:
                return None
        if (
            fact is not None
            and event in normal_report_events
            and fact.trade_quantity is None
            and fact.broker_sequence is not None
            and fact.stream is not None
            and fact.broker_sequence <= self.broker_sequences.get(fact.stream, -1)
            and self._is_stale_non_regressive_report(event, report)
        ):
            return None
        return self._commit(
            event, evidence, fact=fact, remember_fact=fact is not None, conflict=None
        )

    def _commit(
        self,
        event: OrderEvent,
        evidence: GuardEvidence,
        *,
        fact: ExternalFact | None,
        remember_fact: bool,
        conflict: ExternalFact | None,
    ) -> TransitionResult | None:
        definition = _TRANSITIONS.get((self.state, event))
        if definition is None:
            raise InvalidOrderTransition(f"undeclared transition {self.state} + {event}")
        if not self._guard_passes(
            definition.guard, evidence, identity_conflict=conflict is not None
        ):
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
        next_conflicts = dict(self.fact_conflicts)
        next_sequences = dict(self.broker_sequences)
        if remember_fact and fact is not None:
            next_facts[fact.identity] = ProcessedFact(fact.fingerprint, fact.trade_quantity)
            if fact.broker_sequence is not None and fact.stream is not None:
                next_sequences[fact.stream] = max(
                    fact.broker_sequence, next_sequences.get(fact.stream, 0)
                )
        if conflict is not None:
            fingerprints = set(next_conflicts.get(conflict.identity, frozenset()))
            fingerprints.add(conflict.fingerprint)
            next_conflicts[conflict.identity] = frozenset(fingerprints)

        # No mutation occurs before all transition, guard, and fact checks pass.
        self.state = definition.target
        self.cumulative_quantity = candidate
        self.processed_facts = MappingProxyType(next_facts)
        self.fact_conflicts = MappingProxyType(next_conflicts)
        self.broker_sequences = MappingProxyType(next_sequences)
        self.version += 1
        return TransitionResult(previous, self.state, event, definition.action, self.version)

    def _guard_passes(
        self, guard: str, evidence: GuardEvidence, *, identity_conflict: bool
    ) -> bool:
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
        report = evidence.broker_report
        reconciliation = evidence.reconciliation
        if guard == "report_uniquely_correlated":
            return bool(
                report
                and report.correlation_count == 1
                and report.status in {BrokerStatus.ACCEPTED, BrokerStatus.ACTIVE}
            )
        if guard == "outcome_definite":
            return bool(
                report
                and report.correlation_count == 1
                and report.definite
                and report.status is BrokerStatus.REJECTED
            )
        if guard == "broker_confirms_canceled":
            return bool(
                report
                and report.correlation_count == 1
                and report.definite
                and report.status is BrokerStatus.CANCELED
            )
        if guard == "broker_confirms_expired":
            return bool(
                report
                and report.definite
                and report.correlation_count == 1
                and report.status is BrokerStatus.EXPIRED
                and report.reported_cumulative.value == 0
            )
        if guard == "broker_confirms_expired_and_leaves_positive":
            return bool(
                report
                and report.definite
                and report.correlation_count == 1
                and report.status is BrokerStatus.EXPIRED
                and self.cumulative_quantity.value < self.quantity.value
            )
        if guard == "conflicting_same_identity":
            return identity_conflict
        if guard == "report_cumulative_mismatch":
            return bool(
                report
                and report.correlation_count == 1
                and report.reported_cumulative != self.cumulative_quantity
            )
        if guard == "report_correlation_ambiguous":
            return bool(
                report
                and (
                    report.correlation_count > 1
                    or (
                        report.correlation_count == 0
                        and reconciliation
                        and reconciliation.visibility_window_passed
                    )
                )
            )
        if reconciliation is None:
            return False
        unique = reconciliation.match_count == 1
        active = reconciliation.status in {BrokerStatus.ACTIVE, BrokerStatus.ACCEPTED}
        if guard == "unique_broker_match":
            return unique and active
        if guard == "visibility_window_passed":
            return bool(
                reconciliation.visibility_window_passed
                and reconciliation.repeated_absence_confirmed
                and reconciliation.match_count == 0
            )
        status_guards = {
            "unique_broker_match_and_definite_rejection": BrokerStatus.REJECTED,
            "unique_broker_match_and_definite_canceled": BrokerStatus.CANCELED,
            "unique_broker_match_and_definite_expired": BrokerStatus.EXPIRED,
        }
        if guard in status_guards:
            return unique and reconciliation.status is status_guards[guard]
        if guard == "unique_broker_match_and_cum_zero":
            return unique and active and self.cumulative_quantity.value == 0
        if guard == "unique_broker_match_and_cum_between_zero_and_quantity":
            return (
                unique
                and reconciliation.status in {BrokerStatus.ACTIVE, BrokerStatus.PARTIALLY_FILLED}
                and 0 < self.cumulative_quantity.value < self.quantity.value
            )
        if guard == "cancel_rejected_and_trade_derived_cum_zero":
            return unique and reconciliation.cancel_rejected and self.cumulative_quantity.value == 0
        if guard == "cancel_rejected_and_trade_derived_cum_between_zero_and_quantity":
            return (
                unique
                and reconciliation.cancel_rejected
                and 0 < self.cumulative_quantity.value < self.quantity.value
            )
        if guard == "original_order_rejected_after_cancel_history":
            return unique and reconciliation.status is BrokerStatus.REJECTED
        return False

    def _is_stale_non_regressive_report(
        self, event: OrderEvent, report: BrokerReportEvidence | None
    ) -> bool:
        if (
            report is None
            or report.correlation_count != 1
            or report.reported_cumulative.value < self.cumulative_quantity.value
            or report.reported_cumulative.value > self.quantity.value
        ):
            return False
        compatible_states = {
            OrderEvent.BROKER_ACCEPTED: {
                OrderState.SUBMITTED,
                OrderState.PARTIALLY_FILLED,
                OrderState.CANCEL_PENDING,
                OrderState.CANCEL_UNKNOWN,
                OrderState.CANCELED,
                OrderState.EXPIRED,
                OrderState.FILLED,
            },
            OrderEvent.BROKER_REJECTED: {OrderState.REJECTED},
            OrderEvent.BROKER_EXPIRED: {OrderState.EXPIRED},
            OrderEvent.CANCEL_CONFIRMED: {OrderState.CANCELED, OrderState.FILLED},
        }
        compatible_statuses = {
            OrderEvent.BROKER_ACCEPTED: {BrokerStatus.ACCEPTED, BrokerStatus.ACTIVE},
            OrderEvent.BROKER_REJECTED: {BrokerStatus.REJECTED},
            OrderEvent.BROKER_EXPIRED: {BrokerStatus.EXPIRED},
            OrderEvent.CANCEL_CONFIRMED: {BrokerStatus.CANCELED},
        }
        return (
            self.state in compatible_states[event] and report.status in compatible_statuses[event]
        )

    def _validate_state_quantity(self) -> None:
        value = self.cumulative_quantity.value
        total = self.quantity.value
        if self.state is OrderState.FILLED and value != total:
            raise ValueError("FILLED recovery requires cumulative quantity == quantity")
        if self.state is OrderState.PARTIALLY_FILLED and not 0 < value < total:
            raise ValueError("PARTIALLY_FILLED recovery requires a partial cumulative quantity")
        if (
            self.state
            in {
                OrderState.REGISTERED,
                OrderState.RISK_PENDING,
                OrderState.APPROVED,
                OrderState.SUBMITTING,
                OrderState.SUBMIT_UNKNOWN,
                OrderState.SUBMITTED,
                OrderState.REJECTED,
                OrderState.FAILED,
            }
            and value != 0
        ):
            raise ValueError(f"{self.state} recovery requires zero cumulative quantity")

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
