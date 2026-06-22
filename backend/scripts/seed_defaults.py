"""Seed creative_types and lead_types from config/defaults.yaml for all clients."""

import os
import sys

import psycopg2
import yaml
from dotenv import load_dotenv

_BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
_CONFIG_PATH = os.path.join(_BACKEND_DIR, "config", "defaults.yaml")


def _load_defaults() -> dict:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def seed_enum_defaults(cur) -> None:
    """Seed creative_types and lead_types for every client in the DB.

    Accepts a live psycopg2 cursor. Caller owns the transaction and commit.
    Safe to call repeatedly — ON CONFLICT DO NOTHING makes it idempotent.
    """
    defaults = _load_defaults()

    cur.execute("SELECT id FROM clients")
    client_ids = [str(row[0]) for row in cur.fetchall()]

    if not client_ids:
        print("  seed_defaults: no clients found — skipping")
        return

    creative_types = defaults.get("creative_types", [])
    lead_types = defaults.get("lead_types", [])

    cur.executemany(
        "INSERT INTO creative_types (client_id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        [(cid, name) for cid in client_ids for name in creative_types],
    )
    cur.executemany(
        "INSERT INTO lead_types (client_id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        [(cid, name) for cid in client_ids for name in lead_types],
    )

    print(
        f"  seed_defaults: {len(creative_types)} creative_types, "
        f"{len(lead_types)} lead_types — {len(client_ids)} client(s)"
    )


def _standalone():
    load_dotenv(os.path.join(_BACKEND_DIR, ".env"))
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "app_db"),
        user=os.getenv("POSTGRES_USER", "app_user"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )
    try:
        with conn:
            with conn.cursor() as cur:
                seed_enum_defaults(cur)
        print("Done.")
    finally:
        conn.close()


if __name__ == "__main__":
    _standalone()
