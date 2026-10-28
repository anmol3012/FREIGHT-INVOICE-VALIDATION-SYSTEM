"""
Weight and Freight Rating Service for Freight Invoice Validation System.
Computes dimensional weight, chargeable weight, selects contractual weight tiers,
and calculates expected base linehaul charges with minimum charge floor enforcement.
"""

import math
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from backend.app.models.rate_card import RateCard, RateTier
from backend.app.models.shipment import Shipment, WeightMeasurement


@dataclass
class WeightEvaluationResult:
    actual_weight_kg: float
    dimensional_weight_kg: float
    chargeable_weight_kg: float
    divisor: float
    rounding_policy: str
    matched_tier: Optional[RateTier]
    tier_sequence: Optional[int]
    tier_rate_per_kg: Optional[float]
    tier_flat_surcharge: float
    raw_linehaul_amount: float
    expected_linehaul_amount: float
    is_minimum_charge_applied: bool
    measurement_source: Optional[str]
    notes: Dict[str, Any]


class WeightRatingService:
    """
    Evaluates physical measurements against contract weight-breaks and tariff rules.
    """

    @staticmethod
    def calculate_dimensional_weight(
        length_cm: float, width_cm: float, height_cm: float, divisor: float = 5000.0
    ) -> float:
        vol = max(0.0, length_cm) * max(0.0, width_cm) * max(0.0, height_cm)
        return round(vol / max(1.0, divisor), 3)

    @classmethod
    def calculate_chargeable_weight(
        cls,
        actual_weight_kg: float,
        length_cm: float,
        width_cm: float,
        height_cm: float,
        divisor: float = 5000.0,
        rounding_policy: str = "CEIL_KG"
    ) -> float:
        dim_wt = cls.calculate_dimensional_weight(length_cm, width_cm, height_cm, divisor)
        raw_chargeable = max(actual_weight_kg, dim_wt)

        if rounding_policy == "CEIL_KG":
            return float(math.ceil(raw_chargeable))
        return round(raw_chargeable, 2)

    @classmethod
    def evaluate_shipment_weight(
        cls,
        shipment: Shipment,
        rate_card: Optional[RateCard],
        rounding_policy: str = "CEIL_KG"
    ) -> WeightEvaluationResult:
        divisor = rate_card.dimensional_weight_divisor if rate_card else 5000.0

        # Prefer certified/accepted origin scale weight measurement if present
        actual_wt = shipment.actual_weight_kg or 0.0
        l = shipment.actual_length_cm or 0.0
        w = shipment.actual_width_cm or 0.0
        h = shipment.actual_height_cm or 0.0
        src = "SHIPMENT_HEADER"

        if shipment.weight_measurements:
            accepted_wm = [wm for wm in shipment.weight_measurements if wm.is_accepted]
            if accepted_wm:
                target_wm = accepted_wm[0]
                actual_wt = target_wm.weight_kg
                if target_wm.length_cm and target_wm.width_cm and target_wm.height_cm:
                    l = target_wm.length_cm
                    w = target_wm.width_cm
                    h = target_wm.height_cm
                src = target_wm.source.value if hasattr(target_wm.source, "value") else str(target_wm.source)

        dim_wt = cls.calculate_dimensional_weight(l, w, h, divisor)
        chargeable_wt = cls.calculate_chargeable_weight(actual_wt, l, w, h, divisor, rounding_policy)

        # Tier matching
        matched_tier: Optional[RateTier] = None
        if rate_card and rate_card.rate_tiers:
            sorted_tiers = sorted(rate_card.rate_tiers, key=lambda t: t.tier_sequence)
            for tier in sorted_tiers:
                if tier.min_weight_kg <= chargeable_wt:
                    if tier.max_weight_kg is None or chargeable_wt <= tier.max_weight_kg:
                        matched_tier = tier
                        break
            if not matched_tier and sorted_tiers:
                matched_tier = sorted_tiers[-1]

        # Linehaul calculation
        min_charge = rate_card.minimum_charge if rate_card else 75.0
        if matched_tier:
            tier_rate = matched_tier.rate_per_kg
            surcharge = matched_tier.flat_surcharge
            raw_amt = round(chargeable_wt * tier_rate + surcharge, 2)
            tier_seq = matched_tier.tier_sequence
        else:
            base_rate = rate_card.base_rate if rate_card else 0.50
            tier_rate = base_rate
            surcharge = 0.0
            raw_amt = round(chargeable_wt * base_rate, 2)
            tier_seq = None

        is_min_applied = raw_amt < min_charge
        final_linehaul = round(max(raw_amt, min_charge), 2)

        return WeightEvaluationResult(
            actual_weight_kg=actual_wt,
            dimensional_weight_kg=dim_wt,
            chargeable_weight_kg=chargeable_wt,
            divisor=divisor,
            rounding_policy=rounding_policy,
            matched_tier=matched_tier,
            tier_sequence=tier_seq,
            tier_rate_per_kg=tier_rate,
            tier_flat_surcharge=surcharge,
            raw_linehaul_amount=raw_amt,
            expected_linehaul_amount=final_linehaul,
            is_minimum_charge_applied=is_min_applied,
            measurement_source=src,
            notes={
                "length_cm": l,
                "width_cm": w,
                "height_cm": h,
                "min_charge": min_charge
            }
        )
