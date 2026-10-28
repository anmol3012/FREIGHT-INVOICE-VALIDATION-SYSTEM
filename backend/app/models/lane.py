from sqlalchemy import Column, String, Float, CheckConstraint, Enum as SAEnum
from sqlalchemy.orm import relationship
from backend.app.core.database import Base
from backend.app.models.enums import LaneStatus

class Lane(Base):
    """
    Transportation lane connecting geographic origin and destination.
    PK format: LANE-000001
    """
    __tablename__ = "lanes"

    lane_id = Column(String(30), primary_key=True, index=True)
    origin_location_code = Column(String(20), nullable=False, index=True)
    destination_location_code = Column(String(20), nullable=False, index=True)
    origin_city = Column(String(50), nullable=False)
    destination_city = Column(String(50), nullable=False)
    origin_country = Column(String(3), nullable=False, default="USA")
    destination_country = Column(String(3), nullable=False, default="USA")
    distance_km = Column(Float, nullable=False)
    status = Column(SAEnum(LaneStatus), nullable=False, default=LaneStatus.ACTIVE)

    __table_args__ = (
        CheckConstraint("distance_km > 0", name="chk_lane_positive_distance"),
    )

    # Relationships
    rate_cards = relationship("RateCard", back_populates="lane")
    shipments = relationship("Shipment", back_populates="lane")
