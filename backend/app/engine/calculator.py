from dataclasses import dataclass, field
from typing import List, Optional, Dict
import math

@dataclass
class ExpectedLineItem:
    charge_type: str        # LINEHAUL, FUEL_SURCHARGE, ACCESSORIAL
    charge_code: str        # LH, FSC, LIFTGATE, DETENTION, etc.
    description: str
    expected_units: float
    expected_rate: float
    expected_amount: float

@dataclass
class CalculationResult:
    billable_weight_lbs: float
    linehaul_amount: float
    fuel_surcharge_amount: float
    accessorial_amount: float
    total_expected_amount: float
    line_items: List[ExpectedLineItem] = field(default_factory=list)
    rate_card_code: Optional[str] = None
    calculation_details: Dict[str, any] = field(default_factory=dict)


class FreightCalculator:
    """
    Deterministic contractual rating engine.
    Calculates expected charges from shipment characteristics,
    contracted rate cards, weight slips, and confirmed delivery events.
    """

    @staticmethod
    def calculate_billable_weight(gross_weight_lbs: float, length_in: float, width_in: float, height_in: float, dim_factor: float = 139.0) -> float:
        """
        Billable weight = max(actual gross weight, dimensional weight).
        Dimensional weight = (Length * Width * Height) / dim_factor
        """
        cubic_inches = max(0.0, length_in) * max(0.0, width_in) * max(0.0, height_in)
        dim_weight = cubic_inches / max(1.0, dim_factor)
        return round(max(gross_weight_lbs, dim_weight), 2)

    @classmethod
    def calculate_expected_charges(
        cls,
        shipment,
        rate_card,
        rate_lane,
        accessorial_rules: List,
        weight_measurement = None,
        delivery_record = None,
        accessorial_events: List = None
    ) -> CalculationResult:
        if accessorial_events is None:
            accessorial_events = []

        line_items: List[ExpectedLineItem] = []
        details: Dict[str, any] = {}

        # 1. Determine Certified Billable Weight
        if weight_measurement:
            gross_wt = weight_measurement.gross_weight_lbs
            l = weight_measurement.length_in or 48.0
            w = weight_measurement.width_in or 40.0
            h = weight_measurement.height_in or 48.0
            dim_factor = weight_measurement.dim_factor or 139.0
            billable_wt = cls.calculate_billable_weight(gross_wt, l, w, h, dim_factor)
        else:
            billable_wt = 1000.0  # default 10 CWT fallback

        details["billable_weight_lbs"] = billable_wt

        # 2. Linehaul calculation
        model = rate_card.base_rate_model if rate_card else "PER_CWT"
        min_charge = rate_lane.minimum_charge if rate_lane else (rate_card.minimum_charge_floor if rate_card else 75.0)

        if model == "PER_CWT":
            cwt = round(billable_wt / 100.0, 4)
            rate = rate_lane.base_rate_cwt if rate_lane else 12.50
            raw_linehaul = round(cwt * rate, 2)
            final_linehaul = max(raw_linehaul, min_charge)
            line_items.append(ExpectedLineItem(
                charge_type="LINEHAUL",
                charge_code="LH",
                description=f"Base Linehaul ({cwt:.2f} CWT @ ${rate:.2f}/CWT, min ${min_charge:.2f})",
                expected_units=cwt,
                expected_rate=rate,
                expected_amount=round(final_linehaul, 2)
            ))
            details["linehaul_model"] = "PER_CWT"
            details["cwt"] = cwt
            details["rate_cwt"] = rate
        elif model == "PER_MILE":
            miles = shipment.distance_miles or 100.0
            rate = rate_lane.base_rate_per_mile if rate_lane else 2.50
            raw_linehaul = round(miles * rate, 2)
            final_linehaul = max(raw_linehaul, min_charge)
            line_items.append(ExpectedLineItem(
                charge_type="LINEHAUL",
                charge_code="LH",
                description=f"Base Linehaul ({miles:.1f} Miles @ ${rate:.2f}/mi, min ${min_charge:.2f})",
                expected_units=miles,
                expected_rate=rate,
                expected_amount=round(final_linehaul, 2)
            ))
            details["linehaul_model"] = "PER_MILE"
            details["miles"] = miles
            details["rate_mile"] = rate
        else: # FLAT
            flat = rate_lane.flat_rate if (rate_lane and rate_lane.flat_rate > 0) else 450.0
            final_linehaul = max(flat, min_charge)
            line_items.append(ExpectedLineItem(
                charge_type="LINEHAUL",
                charge_code="LH",
                description=f"Flat Linehaul Rate (min ${min_charge:.2f})",
                expected_units=1.0,
                expected_rate=flat,
                expected_amount=round(final_linehaul, 2)
            ))
            details["linehaul_model"] = "FLAT"

        linehaul_amount = round(final_linehaul, 2)

        # 3. Fuel Surcharge (FSC)
        fuel_index = getattr(shipment, "current_fuel_index", 3.85) or 3.85
        base_peg = rate_card.fuel_base_price if rate_card else 3.00
        step_pct = rate_card.fuel_surcharge_pct_per_interval if rate_card else 0.005

        if fuel_index > base_peg:
            fuel_delta = fuel_index - base_peg
            intervals = math.floor((fuel_delta + 1e-6) / 0.05)
            fsc_pct = round(intervals * step_pct, 4)
        else:
            fsc_pct = 0.0

        fsc_amount = round(linehaul_amount * fsc_pct, 2)
        if fsc_amount > 0:
            line_items.append(ExpectedLineItem(
                charge_type="FUEL_SURCHARGE",
                charge_code="FSC",
                description=f"Fuel Surcharge ({fsc_pct*100:.2f}% of Linehaul @ ${fuel_index:.2f}/gal diesel)",
                expected_units=1.0,
                expected_rate=fsc_amount,
                expected_amount=fsc_amount
            ))
        details["fsc_pct"] = fsc_pct
        details["fsc_amount"] = fsc_amount

        # 4. Accessorial Charges
        rule_map = {r.code.upper(): r for r in accessorial_rules}
        total_accessorials = 0.0

        # Check Liftgate
        # Entitled ONLY IF delivery record shows liftgate actually used OR ground delivery required
        liftgate_used = False
        if delivery_record:
            liftgate_used = bool(delivery_record.liftgate_actually_used)
        elif shipment.dock_type in ["GROUND_LEVEL", "RESIDENTIAL"]:
            liftgate_used = True

        if liftgate_used and "LIFTGATE" in rule_map:
            lg_rule = rule_map["LIFTGATE"]
            lg_fee = round(lg_rule.unit_rate, 2)
            line_items.append(ExpectedLineItem(
                charge_type="ACCESSORIAL",
                charge_code="LIFTGATE",
                description="Liftgate Delivery Service (Verified on Delivery Record)",
                expected_units=1.0,
                expected_rate=lg_fee,
                expected_amount=lg_fee
            ))
            total_accessorials += lg_fee

        # Check Detention
        recorded_dwell = 0
        if delivery_record:
            recorded_dwell = delivery_record.detention_minutes_recorded or 0
        
        if "DETENTION" in rule_map:
            det_rule = rule_map["DETENTION"]
            free_min = det_rule.free_time_minutes or 120
            if recorded_dwell > free_min:
                billable_min = recorded_dwell - free_min
                hours = round(billable_min / 60.0, 2)
                hourly_rate = det_rule.unit_rate or 75.0
                det_fee = round(hours * hourly_rate, 2)
                line_items.append(ExpectedLineItem(
                    charge_type="ACCESSORIAL",
                    charge_code="DETENTION",
                    description=f"Detention at Dock ({billable_min} min billable beyond {free_min} min free time)",
                    expected_units=hours,
                    expected_rate=hourly_rate,
                    expected_amount=det_fee
                ))
                total_accessorials += det_fee

        # Check other authorized events (RESIDENTIAL, INSIDE_DELIVERY, HAZMAT, etc.)
        for event in accessorial_events:
            code = event.code.upper()
            if code in ["LIFTGATE", "DETENTION"]:
                continue # Handled with proof above
            if code in rule_map and event.authorized:
                rule = rule_map[code]
                if rule.rate_type == "FLAT":
                    fee = rule.unit_rate
                elif rule.rate_type == "PER_CWT":
                    fee = round((billable_wt / 100.0) * rule.unit_rate, 2)
                else:
                    fee = round(rule.unit_rate * (event.quantity_or_duration or 1.0), 2)
                
                if rule.min_charge and fee < rule.min_charge:
                    fee = rule.min_charge
                if rule.max_charge and fee > rule.max_charge:
                    fee = rule.max_charge

                fee = round(fee, 2)
                line_items.append(ExpectedLineItem(
                    charge_type="ACCESSORIAL",
                    charge_code=code,
                    description=f"{rule.name} ({event.proof_document_ref or 'Verified'})",
                    expected_units=event.quantity_or_duration or 1.0,
                    expected_rate=rule.unit_rate,
                    expected_amount=fee
                ))
                total_accessorials += fee

        total_accessorials = round(total_accessorials, 2)
        total_expected = round(linehaul_amount + fsc_amount + total_accessorials, 2)

        return CalculationResult(
            billable_weight_lbs=billable_wt,
            linehaul_amount=linehaul_amount,
            fuel_surcharge_amount=fsc_amount,
            accessorial_amount=total_accessorials,
            total_expected_amount=total_expected,
            line_items=line_items,
            rate_card_code=rate_card.rate_card_code if rate_card else "STANDARD",
            calculation_details=details
        )
