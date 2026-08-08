"""
Loads the generated CSVs into Postgres.

Reads the schema file, then bulk-loads each table with COPY (much faster than
row-by-row inserts for 100k rows). Empty reason_id cells come in as NULL.

Connection comes from env vars, falling back to a local default:
    PGHOST (localhost) PGPORT (5432) PGDATABASE (payments)
    PGUSER (postgres)  PGPASSWORD ('')
or set a single DATABASE_URL.

Run:  python scripts/load_data.py
"""

import os

import psycopg2

BASE = os.path.dirname(os.path.dirname(__file__))
DATA = os.path.join(BASE, "data")
SCHEMA_FILE = os.path.join(BASE, "sql", "01_schema.sql")

# dimensions first, then the fact table (foreign keys depend on them)
LOAD_ORDER = [
    ("users", "users.csv"),
    ("banks", "banks.csv"),
    ("payment_modes", "payment_modes.csv"),
    ("devices", "devices.csv"),
    ("merchants", "merchants.csv"),
    ("failure_reasons", "failure_reasons.csv"),
    ("transactions", "transactions.csv"),
]


def connect():
    url = os.environ.get("DATABASE_URL")
    if url:
        return psycopg2.connect(url)
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ.get("PGDATABASE", "payments"),
        user=os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("PGPASSWORD", ""),
    )


def run_schema(cur):
    with open(SCHEMA_FILE) as f:
        cur.execute(f.read())
    print("schema created")


def copy_table(cur, table, filename):
    path = os.path.join(DATA, filename)
    with open(path) as f:
        cur.copy_expert(
            f"COPY {table} FROM STDIN WITH (FORMAT csv, HEADER true, NULL '')",
            f,
        )
    cur.execute(f"SELECT count(*) FROM {table}")
    print(f"  {table:<16} {cur.fetchone()[0]:>8,} rows")


def main():
    conn = connect()
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            run_schema(cur)
            print("loading:")
            for table, filename in LOAD_ORDER:
                copy_table(cur, table, filename)
        conn.commit()
        print("done.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
