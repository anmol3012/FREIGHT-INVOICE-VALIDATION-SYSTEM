import math
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass
class ExpectedChargeItem:
    charge_type: str        # BASE_LINEHAUL, FUEL_SURCHARGE, ACCESSORIAL
    accessorial_id: Optional[str]
    charge_code: str        # LH, FSC, LIFTGATE, DETENTION, etc.
    description: str
    quantity: float
    unit_of_measure: str    # KG, KM, HOUR, FLAT
    unit_rate: float
    expected_amount: float
    evidence_reference: Optional[str] = None
    source_reference: Optional[str] = None

@dataclass
class ContractCalculationResult:
    dimensional_weight_kg: float
    chargeable_weight_kg: float
    rate_card_id: Optional[str]
    rate_tier_id: Optional[str]
    base_linehaul_amount: float
    fuel_surcharge_amount: float
    accessorials_amount: float
    total_expected_amount: float
    charge_items: List[ExpectedChargeItem] = field(default_factory=list)
    calculation_notes: Dict[str, Any] = field(default_factory=dict)


class ContractualFreightCalculator:
    """
    Deterministic Contractual Rating Engine.
    Computes exact expected freight charges based on shipment physicals,
    contract rate cards, weight-break tiers, accessorial catalog rules,
    and destination delivery evidence.
    """

    @staticmethod
    def calculate_dimensional_weight(length_cm: float, width_cm: float, height_cm: float, divisor: float = 5000.0) -> float:
        """
        dimensional_weight_kg = (length_cm * width_cm * height_cm) / dimensional_weight_divisor
        """
        vol_cm3 = max(0.0, length_cm) * max(0.0, width_cm) * max(0.0, height_cm)
        return round(vol_cm3 / max(1.0, divisor), 3)

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
        """
        chargeable_weight_kg = max(actual_weight_kg, dimensional_weight_kg)
        """
        dim_wt = cls.calculate_dimensional_weight(length_cm, width_cm, height_cm, divisor)
        raw_chargeable = max(actual_weight_kg, dim_wt)

        if rounding_policy == "CEIL_KG":
            return float(math.ceil(raw_chargeable))
        return round(raw_chargeable, 2)

    @classmethod
    def rate_shipment(
        cls,
        shipment,
        rate_card,
        delivery_evidence=None,
        shipment_accessorials: List = None,
        weight_rounding: str = "CEIL_KG"
    ) -> ContractCalculationResult:
        if shipment_accessorials is None:
            shipment_accessorials = []

        divisor = rate_card.dimensional_weight_divisor if rate_card else 5000.0
        l = shipment.actual_length_cm or 120.0
        w = shipment.actual_width_cm or 80.0
        h = shipment.actual_height_cm or 100.0
        actual_wt = shipment.actual_weight_kg or 100.0

        dim_wt = cls.calculate_dimensional_weight(l, w, h, divisor)
        chargeable_wt = cls.calculate_chargeable_weight(actual_wt, l, w, h, divisor, rounding_policy=weight_rounding)

        charge_items: List[ExpectedChargeItem] = []
        calc_notes: Dict[str, Any] = {
            "dim_weight_kg": dim_wt,
            "chargeable_weight_kg": chargeable_wt,
            "divisor": divisor
        }

        # 1. Linehaul Rating using RateTiers
        linehaul_amount = 0.0
        matched_tier = None

        if rate_card and rate_card.rate_tiers:
            # Sort tiers by sequence
            sorted_tiers = sorted(rate_card.rate_tiers, key=lambda t: t.tier_sequence)
            for tier in sorted_tiers:
                if tier.min_weight_kg <= chargeable_wt:
                    if tier.max_weight_kg is None or chargeable_wt <= tier.max_weight_kg:
                        matched_tier = tier
                        break
            if not matched_tier and sorted_tiers:
                matched_tier = sorted_tiers[-1] # fallback to highest tier

        if matched_tier:
            tier_rate = matched_tier.rate_per_kg
            raw_linehaul = round(chargeable_wt * tier_rate + matched_tier.flat_surcharge, 2)
            linehaul_amount = max(raw_linehaul, rate_card.minimum_charge)
            charge_items.append(ExpectedChargeItem(
                charge_type="BASE_LINEHAUL",
                accessorial_id=None,
                charge_code="LH",
                description=f"Base Linehaul (Tier {matched_tier.tier_sequence}: {chargeable_wt:.1f} kg @ ${tier_rate:.4f}/kg, min ${rate_card.minimum_charge:.2f})",
                quantity=chargeable_wt,
                unit_of_measure="KG",
                unit_rate=tier_rate,
                expected_amount=round(linehaul_amount, 2),
                source_reference=rate_card.rate_card_id
            ))
            calc_notes["matched_tier_id"] = matched_tier.rate_tier_id
            calc_notes["tier_rate_per_kg"] = tier_rate
        else:
            # Fallback flat minimum
            min_chg = rate_card.minimum_charge if rate_card else 85.0
            linehaul_amount = min_chg
            charge_items.append(ExpectedChargeItem(
                charge_type="BASE_LINEHAUL",
                accessorial_id=None,
                charge_code="LH",
                description=f"Base Linehaul (Contract Minimum Charge ${min_chg:.2f})",
                quantity=1.0,
                unit_of_measure="FLAT",
                unit_rate=min_chg,
                expected_amount=round(min_chg, 2),
                source_reference=rate_card.rate_card_id if rate_card else "DEFAULT"
            ))

        linehaul_amount = round(linehaul_amount, 2)

        # 2. Contractual Fuel Surcharge (FSC)
        # Baseline standard is 14% of base linehaul
        fsc_pct = 0.14
        fsc_amount = round(linehaul_amount * fsc_pct, 2)
        charge_items.append(ExpectedChargeItem(
            charge_type="FUEL_SURCHARGE",
            accessorial_id=None,
            charge_code="FSC",
            description=f"Standard Fuel Surcharge ({fsc_pct*100:.1f}% of Linehaul)",
            quantity=1.0,
            unit_of_measure="FLAT",
            unit_rate=fsc_amount,
            expected_amount=fsc_amount,
            source_reference=rate_card.rate_card_id if rate_card else "FSC_INDEX"
        ))

        # 3. Accessorial Charges
        total_accessorials = 0.0

        for sa in shipment_accessorials:
            acc = sa.accessorial
            if not acc or not sa.authorized:
                continue

            code = acc.accessorial_code.upper()
            fee = 0.0
            evidence_ref = sa.evidence_reference or (delivery_evidence.signed_pod_ref if delivery_evidence else None)

            # Evidence Verification Rules
            if acc.requires_evidence:
                if code == "LIFTGATE":
                    # Entitled ONLY IF delivery evidence confirms liftgate was deployed
                    liftgate_deployed = False
                    if delivery_evidence and delivery_evidence.liftgate_actually_used:
                        liftgate_deployed = True
                    if not liftgate_deployed:
                        continue # Expected charge is 0.00!

                elif code == "DETENTION":
                    # Entitled ONLY IF recorded dwell exceeds 120 minutes free time
                    dwell_minutes = delivery_evidence.detention_minutes_recorded if delivery_evidence else 0
                    if dwell_minutes <= 120:
                        continue # No detention entitled within free time!
                    billable_mins = dwell_minutes - 120
                    billable_hours = round(billable_mins / 60.0, 2)
                    fee = round(billable_hours * acc.rate_amount, 2)
                    charge_items.append(ExpectedChargeItem(
                        charge_type="ACCESSORIAL",
                        accessorial_id=acc.accessorial_id,
                        charge_code=code,
                        description=f"{acc.description} ({billable_mins} min billable beyond 120 min free time)",
                        quantity=billable_hours,
                        unit_of_measure="HOUR",
                        unit_rate=acc.rate_amount,
                        expected_amount=fee,
                        evidence_reference=evidence_ref,
                        source_reference=acc.accessorial_id
                    ))
                    total_accessorials += fee
                    continue

            # Standard charge method evaluation
            if acc.charge_method.value == "FLAT":
                fee = round(acc.rate_amount * (sa.quantity or 1.0), 2)
                uom = "FLAT"
                qty = sa.quantity or 1.0
            elif acc.charge_method.value == "PER_KG":
                fee = round(chargeable_wt * acc.rate_amount, 2)
                uom = "KG"
                qty = chargeable_wt
            elif acc.charge_method.value == "PERCENTAGE":
                fee = round(linehaul_amount * (acc.rate_amount / 100.0), 2)
                uom = "FLAT"
                qty = 1.0
            else:
                fee = round(acc.rate_amount * (sa.quantity or 1.0), 2)
                uom = "FLAT"
                qty = sa.quantity or 1.0

            charge_items.append(ExpectedChargeItem(
                charge_type="ACCESSORIAL",
                accessorial_id=acc.accessorial_id,
                charge_code=code,
                description=acc.description,
                quantity=qty,
                unit_of_measure=uom,
                unit_rate=acc.rate_amount,
                expected_amount=fee,
                evidence_reference=evidence_ref,
                source_reference=acc.accessorial_id
            ))
            total_accessorials += fee

        total_accessorials = round(total_accessorials, 2)
        total_expected = round(linehaul_amount + fsc_amount + total_accessorials, 2)

        return ContractCalculationResult(
            dimensional_weight_kg=dim_wt,
            chargeable_weight_kg=chargeable_wt,
            rate_card_id=rate_card.rate_card_id if rate_card else None,
            rate_tier_id=matched_tier.rate_tier_id if matched_tier else None,
            base_linehaul_amount=linehaul_amount,
            fuel_surcharge_amount=fsc_amount,
            accessorials_amount=total_accessorials,
            total_expected_amount=total_expected,
            charge_items=charge_items,
            calculation_notes=calc_notes
        )

# Backward compatibility alias
FreightCalculator = ContractualFreightCalculator
