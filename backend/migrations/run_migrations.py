import glob
import os
import time

import psycopg2
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = os.getenv("POSTGRES_PORT", "5432")
DB_NAME     = os.getenv("POSTGRES_DB", "app_db")
DB_USER     = os.getenv("POSTGRES_USER", "app_user")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")


def wait_for_db(retries: int = 10, delay: float = 2.0) -> psycopg2.extensions.connection:
    for attempt in range(1, retries + 1):
        try:
            conn = psycopg2.connect(
                host=DB_HOST, port=DB_PORT,
                dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
            )
            print(f"Connected to database on attempt {attempt}.")
            return conn
        except psycopg2.OperationalError as e:
            if attempt == retries:
                raise RuntimeError(f"Database not reachable after {retries} attempts: {e}") from e
            print(f"Database not ready (attempt {attempt}/{retries}), retrying in {delay}s…")
            time.sleep(delay)


def existing_tables(cur) -> set:
    """Return the set of table names already in the database."""
    cur.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
    )
    return {row[0] for row in cur.fetchall()}


def run_migrations():
    conn = wait_for_db()
    conn.autocommit = False

    migrations_dir = os.path.dirname(__file__)
    sql_files = sorted(glob.glob(os.path.join(migrations_dir, "*.sql")))

    if not sql_files:
        print("No SQL migration files found.")
        return

    try:
        with conn.cursor() as cur:
            tables = existing_tables(cur)

        applied_count = 0
        for path in sql_files:
            filename = os.path.basename(path)
            with open(path, "r") as f:
                sql = f.read()

            # Skip files whose target table already exists
            # (detected by looking for "CREATE TABLE IF NOT EXISTS <name>" in the file)
            import re
            targets = re.findall(
                r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)", sql, re.IGNORECASE
            )
            if targets and all(t in tables for t in targets):
                print(f"Skipping {filename} (tables already exist: {', '.join(targets)}).")
                continue

            print(f"Running {filename}...", end=" ")
            try:
                with conn.cursor() as cur:
                    cur.execute(sql)
                conn.commit()
                print("OK")
                applied_count += 1
            except Exception as e:
                conn.rollback()
                print(f"\nFailed on {filename}: {e}")
                raise

        if applied_count:
            print(f"\n{applied_count} migration(s) applied successfully.")
        else:
            print("\nDatabase already up to date — nothing to apply.")
    finally:
        conn.close()


if __name__ == "__main__":
    run_migrations()
