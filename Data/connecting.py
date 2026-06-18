import pandas as pd
from db import engine, cloud_engine
from dataSourcing import build_crypto_dataframe


merged_df = build_crypto_dataframe(365)
print(merged_df.dtypes)

with engine.connect() as conn:
    print("Connected!")

merged_df.to_sql(
    "crypto_prices",
    engine,
    if_exists="replace",
    index=False
)
print(merged_df.dtypes)

query = "SELECT btc_prices FROM crypto_prices WHERE btc_prices > 100"
print(pd.read_sql(query, engine))

merged_df.to_sql(
    "crypto_prices", 
    cloud_engine, 
    if_exists="replace", 
    index=False)