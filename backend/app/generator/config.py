"""
Configuration profiles and probability distributions for the synthetic data generator.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple

@dataclass(frozen=True)
class GeneratorProfile:
    name: str
    num_carriers: int
    num_lanes: int
    num_accessorials: int
    num_shipments: int
    num_invoices: int
    seed: int = 20261022
    weight_rounding: str = "CEIL_KG" # "CEIL_KG" or "ROUND_2DEC"

PROFILES: Dict[str, GeneratorProfile] = {
    "test": GeneratorProfile(
        name="test",
        num_carriers=5,
        num_lanes=10,
        num_accessorials=6,
        num_shipments=30,
        num_invoices=25,
        seed=20261022
    ),
    "starter": GeneratorProfile(
        name="starter",
        num_carriers=20,
        num_lanes=45,
        num_accessorials=6,
        num_shipments=250,
        num_invoices=200,
        seed=20261022
    ),
    "full": GeneratorProfile(
        name="full",
        num_carriers=100,
        num_lanes=250,
        num_accessorials=8,
        num_shipments=20000,
        num_invoices=15000,
        seed=20261022
    )
}

# Major US Logistics Hubs (Location Code, City, Country)
LOGISTICS_HUBS: List[Tuple[str, str, str]] = [
    ("ATL-01", "Atlanta", "USA"),
    ("ORD-01", "Chicago", "USA"),
    ("DFW-01", "Dallas", "USA"),
    ("LAX-01", "Los Angeles", "USA"),
    ("JFK-01", "New York", "USA"),
    ("SEA-01", "Seattle", "USA"),
    ("MIA-01", "Miami", "USA"),
    ("DEN-01", "Denver", "USA"),
    ("PHL-01", "Philadelphia", "USA"),
    ("IAH-01", "Houston", "USA"),
    ("PHX-01", "Phoenix", "USA"),
    ("CLT-01", "Charlotte", "USA"),
    ("DTW-01", "Detroit", "USA"),
    ("MEM-01", "Memphis", "USA"),
    ("IND-01", "Indianapolis", "USA"),
    ("MCI-01", "Kansas City", "USA"),
    ("CMH-01", "Columbus", "USA"),
    ("BNA-01", "Nashville", "USA"),
    ("MSP-01", "Minneapolis", "USA"),
    ("SLC-01", "Salt Lake City", "USA"),
]

CARRIER_SEEDS: List[Tuple[str, str]] = [
    ("ODFL", "Old Dominion Freight Line"),
    ("FXFE", "FedEx Freight"),
    ("KNIG", "Knight-Swift Transportation"),
    ("SAIA", "Saia Motor Freight"),
    ("ABFS", "ABF Freight System"),
    ("XPOF", "XPO Logistics"),
    ("ESTE", "Estes Express Lines"),
    ("RLCA", "R+L Carriers"),
    ("YELL", "Yellow Transportation"),
    ("AACT", "AAA Cooper Transportation"),
    ("SEFL", "Southeastern Freight Lines"),
    ("CTII", "Central Transport"),
    ("DAFG", "Dayton Freight Lines"),
    ("PITT", "Pitt Ohio Express"),
    ("CWCE", "Con-way Freight"),
    ("UPGF", "UPS Freight"),
    ("MTRC", "Matson Logistics"),
    ("AVER", "Averitt Express"),
    ("CVLG", "Covenant Logistics"),
    ("WERN", "Werner Enterprises"),
    ("JBHT", "J.B. Hunt Transport"),
    ("SCHN", "Schneider National"),
    ("USXI", "U.S. Xpress Enterprises"),
    ("SWFT", "Swift Transportation"),
    ("HEAR", "Heartland Express"),
    ("MART", "Marten Transport"),
    ("CRST", "CRST International"),
    ("PTSI", "P.A.M. Transportation"),
    ("COSS", "Cowan Systems"),
    ("DAYR", "Daylight Transport")
]

ACCESSORIAL_CATALOG: List[Tuple[str, str, str, float, bool]] = [
    ("LIFTGATE", "Hydraulic liftgate delivery service", "FLAT", 85.0, True),
    ("DETENTION", "Driver facility detention beyond 120-min free time", "PER_HOUR", 75.0, True),
    ("RESIDENTIAL", "Residential or non-commercial delivery surcharge", "FLAT", 65.0, True),
    ("INSIDE_DELIVERY", "Inside facility delivery beyond loading dock", "FLAT", 75.0, True),
    ("HAZMAT", "Hazardous materials handling and documentation", "FLAT", 125.0, True),
    ("APPOINTMENT", "Guaranteed specific delivery appointment time", "FLAT", 40.0, True),
    ("RECONSIGNMENT", "In-transit route or destination reconsignment", "FLAT", 110.0, True),
    ("OVERSIZED", "Oversized dimensional cargo handling", "PERCENTAGE", 15.0, False),
]
