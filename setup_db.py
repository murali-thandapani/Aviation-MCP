"""
================================================================================
DATABASE SETUP SCRIPT
================================================================================
File        : setup_db.py
Role        : One-time script that creates and seeds the SQLite database
              (flights.db) used by Agent 2 — Flight Operations.

When to run
-----------
  • Once, before starting mcp_server.py for the first time.
  • Again, to reset / re-seed the database after schema changes.
  • In a CI pipeline's setup step before running integration tests.

Libraries Used
--------------
  sqlite3  (stdlib)
    The Python standard library's interface to SQLite — a serverless,
    file-based relational database engine.

    Why SQLite for this project?
    ────────────────────────────
    1. Zero infrastructure:
       No server process to start, no port to open, no credentials to manage.
       The entire database is a single .db file that lives next to the code.

    2. Bundled with Python:
       sqlite3 is part of the CPython standard library since Python 2.5.
       No pip install is needed — reduces deployment friction.

    3. ACID compliant:
       SQLite supports transactions, so a failed bulk INSERT leaves the table
       in a consistent state (no partial writes).

    4. SQL standard:
       Parameterised queries, WHERE clauses, ORDER BY, JOINs — all standard
       SQL syntax.  Migrating to PostgreSQL later requires only changing the
       driver (psycopg2) and the connection string, not the SQL itself.

    5. Right-sized:
       For a read-mostly dataset of ~100 flights, SQLite handles thousands of
       queries per second.  A full RDBMS would be over-engineering.

    Key sqlite3 concepts used in this file
    ───────────────────────────────────────
    • sqlite3.connect(path)
        Opens (or creates) a database file at the given path.

    • conn.cursor()
        Returns a Cursor object for executing SQL statements.

    • c.execute(sql)
        Executes a single SQL statement.

    • c.executemany(sql, data)
        Executes a SQL statement once for each item in `data`.
        More efficient than a Python loop of c.execute() calls because
        sqlite3 can batch the writes into a single transaction internally.

    • CREATE TABLE IF NOT EXISTS
        Idempotent: running this script twice does not fail or duplicate the
        schema.

    • INSERT OR REPLACE
        If a row with the same PRIMARY KEY already exists, it is replaced.
        Allows re-running the script to refresh data without first dropping
        the table.

    • conn.commit()
        Flushes pending writes to disk.  Without commit(), changes are only
        in memory and are lost when the connection closes.

    • conn.close()
        Releases the file lock on flights.db.  Good practice even though
        Python's garbage collector would eventually close it.

  os  (stdlib)
    Used to resolve the DB file path relative to this script, ensuring
    setup_db.py creates flights.db in the correct directory regardless of
    the caller's working directory.

Schema Design Notes
-------------------
  Column          Type     Rationale
  ─────────────── ──────── ─────────────────────────────────────────────────
  flight_number   TEXT PK  IATA codes are alphanumeric strings, not integers.
                            Using TEXT avoids leading-zero or suffix-letter issues.
  airline         TEXT     Full airline name for display purposes.
  origin          TEXT     Full city/airport name (human-readable).
  origin_code     TEXT     3-letter IATA code for the origin airport.
  destination     TEXT     Full city/airport name.
  destination_code TEXT    3-letter IATA code for the destination airport.
  departure_time  TEXT     HH:MM string in local time.  Stored as TEXT because
                            SQLite has no native TIME type; ISO 8601 strings sort
                            correctly lexicographically.
  arrival_time    TEXT     Same rationale as departure_time.
  aircraft        TEXT     Aircraft type for crew briefing purposes.
  status          TEXT     Operational status: "On Time", "Delayed", "Cancelled".

Usage
-----
  python setup_db.py
================================================================================
"""

import sqlite3   # Embedded relational database
import os        # Path resolution


# ── Path Configuration ────────────────────────────────────────────────────────
# Always create flights.db in the same directory as this script.
# os.path.abspath(__file__) gives the absolute path to setup_db.py itself,
# os.path.dirname(...) strips the filename, leaving just the directory.
_DIR     = os.path.dirname(os.path.abspath(__file__))
_DB_PATH = os.path.join(_DIR, "flights.db")


# ── Schema ────────────────────────────────────────────────────────────────────
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS flights (
    flight_number    TEXT PRIMARY KEY,
    airline          TEXT NOT NULL,
    origin           TEXT NOT NULL,
    origin_code      TEXT NOT NULL,
    destination      TEXT NOT NULL,
    destination_code TEXT NOT NULL,
    departure_time   TEXT NOT NULL,
    arrival_time     TEXT NOT NULL,
    aircraft         TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'On Time'
)
"""

# ── Seed Data ─────────────────────────────────────────────────────────────────
# Tuple order must match the column order in the INSERT statement below:
# (flight_number, airline, origin, origin_code, destination, destination_code,
#  departure_time, arrival_time, aircraft, status)
_FLIGHTS: list[tuple] = [
    # ── Qatar Airways ────────────────────────────────────────────────────────
    ("QR120",  "Qatar Airways",       "Doha",                "DOH", "London Heathrow",   "LHR", "02:35", "07:50", "Boeing 777-300ER",   "On Time"),
    ("QR007",  "Qatar Airways",       "Doha",                "DOH", "New York JFK",      "JFK", "09:15", "15:30", "Airbus A350-1000",   "On Time"),
    ("QR305",  "Qatar Airways",       "Doha",                "DOH", "Paris CDG",         "CDG", "08:00", "12:45", "Airbus A380",        "Delayed"),
    ("QR948",  "Qatar Airways",       "Doha",                "DOH", "Sydney",            "SYD", "22:00", "17:10", "Airbus A380",        "On Time"),
    ("QR570",  "Qatar Airways",       "Doha",                "DOH", "Tokyo Narita",      "NRT", "01:45", "16:20", "Boeing 787-8",       "On Time"),
    ("QR528",  "Qatar Airways",       "Doha",                "DOH", "Singapore Changi",  "SIN", "02:20", "12:35", "Airbus A350-900",    "On Time"),
    # ── Emirates ─────────────────────────────────────────────────────────────
    ("EK201",  "Emirates",            "Dubai",               "DXB", "London Heathrow",   "LHR", "08:30", "13:10", "Airbus A380",        "On Time"),
    ("EK505",  "Emirates",            "Dubai",               "DXB", "New York JFK",      "JFK", "14:20", "19:45", "Boeing 777-300ER",   "On Time"),
    ("EK432",  "Emirates",            "Dubai",               "DXB", "Singapore Changi",  "SIN", "23:55", "12:15", "Boeing 777-200LR",   "On Time"),
    ("EK407",  "Emirates",            "Dubai",               "DXB", "Sydney",            "SYD", "22:05", "17:20", "Airbus A380",        "On Time"),
    # ── British Airways ───────────────────────────────────────────────────────
    ("BA105",  "British Airways",     "London Heathrow",     "LHR", "New York JFK",      "JFK", "10:25", "13:20", "Boeing 747-400",     "On Time"),
    ("BA007",  "British Airways",     "London Heathrow",     "LHR", "Sydney",            "SYD", "21:00", "05:45", "Boeing 777-200ER",   "On Time"),
    ("BA011",  "British Airways",     "London Heathrow",     "LHR", "Singapore Changi",  "SIN", "21:30", "17:15", "Boeing 787-9",       "Delayed"),
    # ── Singapore Airlines ────────────────────────────────────────────────────
    ("SQ321",  "Singapore Airlines",  "Singapore Changi",    "SIN", "London Heathrow",   "LHR", "23:25", "06:00", "Airbus A350-900",    "On Time"),
    ("SQ25",   "Singapore Airlines",  "Singapore Changi",    "SIN", "New York JFK",      "JFK", "23:05", "07:55", "Airbus A350-900ULR", "On Time"),
    # ── Air India ─────────────────────────────────────────────────────────────
    ("AI101",  "Air India",           "Mumbai",              "BOM", "London Heathrow",   "LHR", "02:15", "07:30", "Boeing 787-8",       "On Time"),
    ("AI144",  "Air India",           "Mumbai",              "BOM", "New York JFK",      "JFK", "01:30", "08:45", "Boeing 777-200LR",   "On Time"),
]

_INSERT_SQL = """
INSERT OR REPLACE INTO flights VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


# ══════════════════════════════════════════════════════════════════════════════
# SETUP FUNCTION
# ══════════════════════════════════════════════════════════════════════════════

def setup_database() -> None:
    """
    Create the flights table (if it does not exist) and insert seed data.

    Uses INSERT OR REPLACE so this function is safe to call multiple times —
    existing rows are updated; new rows are added; no duplicates are created.
    """
    conn = sqlite3.connect(_DB_PATH)
    c    = conn.cursor()

    # Create schema
    c.execute(_CREATE_TABLE_SQL)

    # Bulk-insert seed data
    # executemany is used (not a loop of execute) because:
    #   1. It is more efficient — sqlite3 batches the writes.
    #   2. The entire operation is atomic: if any row fails, none are committed.
    c.executemany(_INSERT_SQL, _FLIGHTS)

    conn.commit()
    conn.close()

    print(f"[OK] flights.db created/updated at: {_DB_PATH}")
    print(f"[OK] {len(_FLIGHTS)} flight records inserted/replaced.")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    setup_database()
