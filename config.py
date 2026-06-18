import os
from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv("COIN_GEKO_API_KEY")
COIN_GEKO_URL = os.getenv("BASE_URL")
POSTGRE_URL = os.getenv("POSTGRE_URL")
NEON_URL = os.getenv("NEON_URL")