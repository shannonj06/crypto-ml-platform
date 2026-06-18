from sqlalchemy import create_engine
from config import POSTGRE_URL, NEON_URL
engine = create_engine(
    POSTGRE_URL
)

cloud_engine = create_engine(
    NEON_URL
)
