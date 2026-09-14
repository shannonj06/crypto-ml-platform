"""
Database engines.

These are built at import time, so anything that imports this module used to
die outright when POSTGRE_URL / NEON_URL were unset — including sources that
need no database at all (Fear & Greed only talks to a public API). Now a
missing URL leaves the engine as None and fails loudly at the point of use
instead, which keeps the credential-free sources runnable on their own.
"""
from sqlalchemy import create_engine

from config import NEON_URL, POSTGRE_URL

engine = create_engine(POSTGRE_URL) if POSTGRE_URL else None
cloud_engine = create_engine(NEON_URL) if NEON_URL else None


def require(db, name):
    """Return `db`, or explain which setting is missing."""
    if db is None:
        raise RuntimeError(
            f"{name} is not set. Put it in your .env for local runs, or add it "
            f"as a repository secret for GitHub Actions."
        )
    return db
