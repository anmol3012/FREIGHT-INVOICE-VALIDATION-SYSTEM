"""
Contract Selection Service for Freight Invoice Validation System.
Resolves contractual rate cards based on carrier, lane, service level,
effective dates, status, and documented precedence rules.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from backend.app.models.rate_card import RateCard
from backend.app.models.enums import RateCardStatus, ServiceLevel


@dataclass
class RateCardSelectionResult:
    rate_card: Optional[RateCard]
    status: str # "FOUND", "EXPIRED", "MISSING", "AMBIGUOUS"
    reason: str
    candidates_count: int = 0
    candidate_ids: List[str] = field(default_factory=list)


class ContractSelector:
    """
    Selects the applicable rate card for a shipment.
    Applies explicit precedence rules when multiple active contracts overlap:
      1. Effective date specificity (shortest validity window).
      2. Most recent contract creation timestamp (`created_at`).
      3. Deterministic lexical identifier ordering (`rate_card_id`).
    """

    @classmethod
    def select_rate_card(
        cls,
        db: Session,
        carrier_id: str,
        lane_id: str,
        service_level: ServiceLevel = ServiceLevel.STANDARD,
        shipment_date: Optional[date] = None
    ) -> RateCardSelectionResult:
        if not carrier_id:
            return RateCardSelectionResult(
                rate_card=None,
                status="MISSING",
                reason="Carrier ID was not provided."
            )

        if not lane_id:
            return RateCardSelectionResult(
                rate_card=None,
                status="MISSING",
                reason="Lane ID was not provided."
            )

        if shipment_date is None:
            shipment_date = date.today()

        # Query all active rate cards for this carrier and lane
        query = db.query(RateCard).filter(
            RateCard.carrier_id == carrier_id,
            RateCard.lane_id == lane_id,
            RateCard.service_level == service_level,
            RateCard.status == RateCardStatus.ACTIVE
        )
        active_cards: List[RateCard] = query.all()

        if not active_cards:
            # Check if there are inactive or expired cards to give an explainable diagnostic
            any_cards = db.query(RateCard).filter(
                RateCard.carrier_id == carrier_id,
                RateCard.lane_id == lane_id
            ).all()

            if any_cards:
                expired = [
                    rc for rc in any_cards
                    if rc.effective_to and rc.effective_to < shipment_date
                ]
                if expired:
                    return RateCardSelectionResult(
                        rate_card=expired[0],
                        status="EXPIRED",
                        reason=f"Rate card {expired[0].rate_card_id} expired on {expired[0].effective_to.isoformat()} before shipment date {shipment_date.isoformat()}.",
                        candidates_count=len(expired),
                        candidate_ids=[rc.rate_card_id for rc in expired]
                    )

            return RateCardSelectionResult(
                rate_card=None,
                status="MISSING",
                reason=f"No active rate cards exist for carrier {carrier_id} on lane {lane_id} with service level {service_level.value}.",
                candidates_count=0
            )

        # Filter by effective date range
        valid_date_cards = [
            rc for rc in active_cards
            if rc.effective_from <= shipment_date and (rc.effective_to is None or rc.effective_to >= shipment_date)
        ]

        if not valid_date_cards:
            # Active cards exist, but none are effective for the given shipment date
            expired_candidates = [
                rc for rc in active_cards
                if rc.effective_to and rc.effective_to < shipment_date
            ]
            if expired_candidates:
                return RateCardSelectionResult(
                    rate_card=expired_candidates[0],
                    status="EXPIRED",
                    reason=f"Rate card {expired_candidates[0].rate_card_id} is active but validity expired on {expired_candidates[0].effective_to.isoformat()} before shipment date {shipment_date.isoformat()}.",
                    candidates_count=len(expired_candidates),
                    candidate_ids=[rc.rate_card_id for rc in expired_candidates]
                )

            return RateCardSelectionResult(
                rate_card=None,
                status="MISSING",
                reason=f"Rate cards exist for carrier {carrier_id} on lane {lane_id}, but none are effective on shipment date {shipment_date.isoformat()}.",
                candidates_count=len(active_cards),
                candidate_ids=[rc.rate_card_id for rc in active_cards]
            )

        if len(valid_date_cards) == 1:
            return RateCardSelectionResult(
                rate_card=valid_date_cards[0],
                status="FOUND",
                reason=f"Applicable rate card {valid_date_cards[0].rate_card_id} resolved successfully.",
                candidates_count=1,
                candidate_ids=[valid_date_cards[0].rate_card_id]
            )

        # Multiple overlapping contracts: apply precedence rules
        def precedence_sort_key(rc: RateCard):
            # 1. Date window specificity (smaller span = more specific)
            if rc.effective_to:
                span = (rc.effective_to - rc.effective_from).days
            else:
                span = 999999
            # 2. Recency (negative timestamp so newest comes first)
            ts = -rc.created_at.timestamp() if rc.created_at else 0
            # 3. Lexical ID tie-breaker
            return (span, ts, rc.rate_card_id)

        sorted_candidates = sorted(valid_date_cards, key=precedence_sort_key)
        best_card = sorted_candidates[0]

        return RateCardSelectionResult(
            rate_card=best_card,
            status="FOUND",
            reason=f"Resolved rate card {best_card.rate_card_id} via precedence rule from {len(valid_date_cards)} candidates.",
            candidates_count=len(valid_date_cards),
            candidate_ids=[rc.rate_card_id for rc in sorted_candidates]
        )
