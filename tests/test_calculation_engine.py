import pytest
from backend.app.engine.calculator import FreightCalculator
from backend.app.models.rate_card import RateCard, RateLane, AccessorialRule
from backend.app.models.shipment import Shipment, WeightMeasurement, DeliveryRecord
from datetime import date, datetime

def test_billable_weight_dimensional():
    # Actual weight 500 lbs, dimensions 48 x 40 x 60 with dim factor 139
    # Cubic inches = 115,200. Dim wt = 115200 / 139 = 828.78 lbs
    billable = FreightCalculator.calculate_billable_weight(
        gross_weight_lbs=500.0, length_in=48.0, width_in=40.0, height_in=60.0, dim_factor=139.0
    )
    assert billable == 828.78
    assert billable > 500.0

def test_billable_weight_heavy_cargo():
    # Dense small cargo: 3000 lbs, 36 x 36 x 36 with dim factor 139
    # Dim weight = 46656 / 139 = 335.65 lbs. Billable should be actual 3000 lbs.
    billable = FreightCalculator.calculate_billable_weight(
        gross_weight_lbs=3000.0, length_in=36.0, width_in=36.0, height_in=36.0, dim_factor=139.0
    )
    assert billable == 3000.0

def test_linehaul_cwt_and_minimum_floor():
    # 500 lbs = 5 CWT. Rate = $12.00/CWT -> Raw $60.00. Min floor = $85.00
    # Expected linehaul should be $85.00
    rc = RateCard(
        rate_card_code="RC-TEST-1",
        carrier_id=1,
        effective_date=date(2026, 1, 1),
        expiration_date=date(2026, 12, 31),
        base_rate_model="PER_CWT",
        minimum_charge_floor=85.0,
        fuel_base_price=3.00,
        fuel_surcharge_pct_per_interval=0.005
    )
    lane = RateLane(
        rate_card_id=1,
        base_rate_cwt=12.00,
        minimum_charge=85.0
    )
    shipment = Shipment(
        bol_number="BOL-TEST-MIN",
        carrier_id=1,
        origin_zip="30301", origin_city="Atlanta", origin_state="GA",
        destination_zip="60601", destination_city="Chicago", destination_state="IL",
        pickup_date=date(2026, 3, 1), delivery_date=date(2026, 3, 3),
        current_fuel_index=3.00 # At peg -> 0% FSC
    )
    wm = WeightMeasurement(
        gross_weight_lbs=500.0,
        length_in=40.0, width_in=40.0, height_in=40.0,
        billable_weight_lbs=500.0
    )
    res = FreightCalculator.calculate_expected_charges(
        shipment=shipment,
        rate_card=rc,
        rate_lane=lane,
        accessorial_rules=[],
        weight_measurement=wm
    )
    assert res.linehaul_amount == 85.0
    assert res.fuel_surcharge_amount == 0.0
    assert res.total_expected_amount == 85.0

def test_fuel_surcharge_calculation():
    # Linehaul = $1000. Diesel = $4.00, Base peg = $3.00, Step = $0.05 per 0.5%
    # Delta = $1.00. Intervals = 20. FSC % = 20 * 0.5% = 10% -> FSC Amount = $100.00
    rc = RateCard(
        rate_card_code="RC-TEST-FSC",
        carrier_id=1,
        effective_date=date(2026, 1, 1),
        expiration_date=date(2026, 12, 31),
        base_rate_model="PER_CWT",
        minimum_charge_floor=50.0,
        fuel_base_price=3.00,
        fuel_surcharge_pct_per_interval=0.005
    )
    lane = RateLane(
        rate_card_id=1,
        base_rate_cwt=10.00,
        minimum_charge=50.0
    )
    shipment = Shipment(
        bol_number="BOL-TEST-FSC",
        carrier_id=1,
        origin_zip="30301", origin_city="Atlanta", origin_state="GA",
        destination_zip="60601", destination_city="Chicago", destination_state="IL",
        pickup_date=date(2026, 3, 1), delivery_date=date(2026, 3, 3),
        current_fuel_index=4.00
    )
    wm = WeightMeasurement(
        gross_weight_lbs=10000.0, # 100 CWT * $10 = $1,000 linehaul
        length_in=48.0, width_in=40.0, height_in=48.0,
        billable_weight_lbs=10000.0
    )
    res = FreightCalculator.calculate_expected_charges(
        shipment=shipment,
        rate_card=rc,
        rate_lane=lane,
        accessorial_rules=[],
        weight_measurement=wm
    )
    assert res.linehaul_amount == 1000.00
    assert res.fuel_surcharge_amount == 100.00
    assert res.total_expected_amount == 1100.00
