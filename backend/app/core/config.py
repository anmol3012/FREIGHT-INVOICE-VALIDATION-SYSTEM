from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="allow")

    PROJECT_NAME: str = "Freight Invoice Validation System"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api"
    
    # Database
    DATABASE_URL: str = f"sqlite:///{BASE_DIR}/freight_validation.db"
    
    # Validation Tolerances
    ABSOLUTE_TOLERANCE_USD: float = 1.00     # $1.00 tolerance
    PERCENTAGE_TOLERANCE: float = 0.01       # 1.0% tolerance
    WEIGHT_TOLERANCE_LBS: float = 20.0       # 20 lbs scale tolerance
    DETENTION_FREE_MINUTES: int = 120        # 2 hours standard free time
    
    # Default Generation Seeds & Scale
    DEFAULT_RANDOM_SEED: int = 20261022
    
    # Scale configurations
    STARTER_CARRIERS: int = 20
    STARTER_SHIPMENTS: int = 250
    STARTER_INVOICES: int = 200
    
    FULL_CARRIERS: int = 100
    FULL_SHIPMENTS: int = 20000
    FULL_INVOICES: int = 15000

settings = Settings()
