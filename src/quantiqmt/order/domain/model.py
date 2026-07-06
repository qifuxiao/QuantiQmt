"""Pure OMS Order aggregate and approved state machine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

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
    OUTCOME_UNKNOWN = "OutcomeUnknown"
    RECONCILE_FOUND_ACTIVE = "ReconcileFoundActive"
    RECONCILE_CONFIRMED_ABSENT = "ReconcileConfirmedAbsent"
    RECONCILE_AMBIGUOUS = "ReconcileAmbiguous"
    PARTIAL_TRADE = "PartialTrade"
    FULL_TRADE = "FullTrade"
    REQUEST_CANCEL = "RequestCancel"
    CANCEL_CONFIRMED = "CancelConfirmed"
    RECONCILE_CANCELED = "ReconcileCanceled"


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
    START_CANCEL_ATTEMPT = "StartCancelAttempt"


class InvalidOrderTransition(ValueError):
    code = "QQ-OMS-5002"


@dataclass(frozen=True, slots=True)
class TransitionResult:
    previous: OrderState
    current: OrderState
    event: OrderEvent
    action: OrderAction
    version: int


_T = tuple[OrderState, OrderEvent]
_TRANSITIONS: dict[_T, tuple[OrderState, OrderAction]] = {
    (OrderState.REGISTERED, OrderEvent.START_RISK): (
        OrderState.RISK_PENDING,
        OrderAction.REQUEST_RISK_EVALUATION,
    ),
    (OrderState.RISK_PENDING, OrderEvent.RISK_PASSED): (
        OrderState.APPROVED,
        OrderAction.PERSIST_ORDER_APPROVED,
    ),
    (OrderState.RISK_PENDING, OrderEvent.RISK_REJECTED): (
        OrderState.REJECTED,
        OrderAction.PERSIST_ORDER_REJECTED,
    ),
    (OrderState.APPROVED, OrderEvent.DISPATCH): (
        OrderState.SUBMITTING,
        OrderAction.START_EXECUTION_ATTEMPT,
    ),
    (OrderState.SUBMITTING, OrderEvent.BROKER_ACCEPTED): (
        OrderState.SUBMITTED,
        OrderAction.MERGE_BROKER_REPORT,
    ),
    (OrderState.SUBMITTING, OrderEvent.BROKER_REJECTED): (
        OrderState.REJECTED,
        OrderAction.MERGE_BROKER_REPORT,
    ),
    (OrderState.SUBMITTING, OrderEvent.OUTCOME_UNKNOWN): (
        OrderState.SUBMIT_UNKNOWN,
        OrderAction.SCHEDULE_RECONCILIATION,
    ),
    (OrderState.SUBMIT_UNKNOWN, OrderEvent.RECONCILE_FOUND_ACTIVE): (
        OrderState.SUBMITTED,
        OrderAction.IMPORT_BROKER_FACTS,
    ),
    (OrderState.SUBMIT_UNKNOWN, OrderEvent.RECONCILE_CONFIRMED_ABSENT): (
        OrderState.FAILED,
        OrderAction.PERSIST_SUBMIT_FAILED,
    ),
    (OrderState.SUBMIT_UNKNOWN, OrderEvent.RECONCILE_AMBIGUOUS): (
        OrderState.SUSPENDED,
        OrderAction.OPEN_RECONCILIATION_CASE,
    ),
    (OrderState.SUBMITTED, OrderEvent.PARTIAL_TRADE): (
        OrderState.PARTIALLY_FILLED,
        OrderAction.RECORD_TRADE,
    ),
    (OrderState.SUBMITTED, OrderEvent.FULL_TRADE): (OrderState.FILLED, OrderAction.RECORD_TRADE),
    (OrderState.PARTIALLY_FILLED, OrderEvent.FULL_TRADE): (
        OrderState.FILLED,
        OrderAction.RECORD_TRADE,
    ),
    (OrderState.SUBMITTED, OrderEvent.REQUEST_CANCEL): (
        OrderState.CANCEL_PENDING,
        OrderAction.START_CANCEL_ATTEMPT,
    ),
    (OrderState.PARTIALLY_FILLED, OrderEvent.REQUEST_CANCEL): (
        OrderState.CANCEL_PENDING,
        OrderAction.START_CANCEL_ATTEMPT,
    ),
    (OrderState.CANCEL_PENDING, OrderEvent.CANCEL_CONFIRMED): (
        OrderState.CANCELED,
        OrderAction.MERGE_BROKER_REPORT,
    ),
    (OrderState.CANCEL_PENDING, OrderEvent.OUTCOME_UNKNOWN): (
        OrderState.CANCEL_UNKNOWN,
        OrderAction.SCHEDULE_RECONCILIATION,
    ),
    (OrderState.CANCEL_PENDING, OrderEvent.FULL_TRADE): (
        OrderState.FILLED,
        OrderAction.RECORD_TRADE,
    ),
    (OrderState.CANCEL_UNKNOWN, OrderEvent.RECONCILE_CANCELED): (
        OrderState.CANCELED,
        OrderAction.IMPORT_BROKER_FACTS,
    ),
    (OrderState.CANCEL_UNKNOWN, OrderEvent.RECONCILE_AMBIGUOUS): (
        OrderState.SUSPENDED,
        OrderAction.OPEN_RECONCILIATION_CASE,
    ),
}


@dataclass(slots=True)
class Order:
    order_id: Identifier
    quantity: Quantity
    state: OrderState = OrderState.REGISTERED
    cumulative_quantity: Quantity = field(default_factory=lambda: Quantity(0))
    version: int = 1
    _processed_facts: set[str] = field(default_factory=set, repr=False)

    def __post_init__(self) -> None:
        self.quantity.require_positive()
        self._assert_quantity(self.cumulative_quantity)

    def transition(
        self,
        event: OrderEvent,
        *,
        guard_satisfied: bool = True,
        cumulative_quantity: Quantity | None = None,
        fact_id: str | None = None,
    ) -> TransitionResult | None:
        if fact_id is not None and fact_id in self._processed_facts:
            return None
        definition = _TRANSITIONS.get((self.state, event))
        if definition is None or not guard_satisfied:
            raise InvalidOrderTransition(f"{self.code}: {self.state} + {event}")
        if event in {OrderEvent.PARTIAL_TRADE, OrderEvent.FULL_TRADE}:
            if cumulative_quantity is None:
                raise InvalidOrderTransition(f"{self.code}: trade requires cumulative quantity")
            self._assert_trade(event, cumulative_quantity)
        previous = self.state
        target, action = definition
        self.state = target
        if cumulative_quantity is not None:
            self.cumulative_quantity = cumulative_quantity
        self.version += 1
        if fact_id is not None:
            self._processed_facts.add(fact_id)
        return TransitionResult(previous, target, event, action, self.version)

    @property
    def code(self) -> str:
        return InvalidOrderTransition.code

    def _assert_quantity(self, value: Quantity) -> None:
        if value.value > self.quantity.value:
            raise ValueError("cumulative quantity exceeds order quantity")

    def _assert_trade(self, event: OrderEvent, value: Quantity) -> None:
        self._assert_quantity(value)
        if value.value < self.cumulative_quantity.value:
            raise InvalidOrderTransition(f"{self.code}: cumulative quantity is not monotonic")
        if event is OrderEvent.PARTIAL_TRADE and not 0 < value.value < self.quantity.value:
            raise InvalidOrderTransition(f"{self.code}: invalid partial cumulative quantity")
        if event is OrderEvent.FULL_TRADE and value != self.quantity:
            raise InvalidOrderTransition(f"{self.code}: full trade must equal order quantity")


def transition_catalog() -> frozenset[tuple[OrderState, OrderEvent, OrderState]]:
    return frozenset(
        (source, event, target) for (source, event), (target, _) in _TRANSITIONS.items()
    )
