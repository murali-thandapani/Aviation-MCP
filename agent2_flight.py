"""
================================================================================
AGENT 2 — FLIGHT OPERATIONS AGENT
================================================================================
MCP Protocol Compliance
-----------------------
Exposes TOOL_DESCRIPTORS so the AgentRegistry can include this agent's tools
in the tools/list response without any knowledge of this file's internals.
The router never imports this module directly — it only calls
registry.call_tool("get_flight_info", {"flight_number": "QR120"}).
================================================================================
"""
import sqlite3
import os
import re
import json

# ── MCP Tool Descriptor ───────────────────────────────────────────────────────
TOOL_DESCRIPTORS: list[dict] = [
    {
        "name": "get_flight_info",
        "description": (
            "Retrieves full flight information from the local SQLite database "
            "for a given IATA flight number. Returns origin, destination, IATA "
            "airport codes, scheduled departure and arrival times, aircraft type, "
            "and operational status. Use when the user provides a flight number "
            "such as QR120, EK201, BA105."
        ),
        "agent_module": "agent2_flight",
        "handler":      "get_flight_info",
        "inputSchema": {
            "type": "object",
            "properties": {
                "flight_number": {
                    "type":        "string",
                    "description": "IATA flight number (e.g. 'QR120', 'EK 201', 'ba-105')"
                }
            },
            "required": ["flight_number"]
        },
        "triggers": []   # Detected by regex pattern in router, not keywords
    },
    {
        "name": "list_all_flights",
        "description": "Returns a summary list of all flights in the database. Useful for showing a flight directory.",
        "agent_module": "agent2_flight",
        "handler":      "list_all_flights",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
        "triggers": ["all flights", "flight list", "show flights"]
    }
]

# ── DB config ─────────────────────────────────────────────────────────────────
_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flights.db")
_SELECT_FLIGHT_SQL = "SELECT * FROM flights WHERE flight_number = ?"
_SELECT_ALL_SQL    = "SELECT flight_number, airline, origin, destination, departure_time, arrival_time, status FROM flights ORDER BY flight_number"

def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def _sanitise(raw: str) -> str:
    return re.sub(r'[\s\-]+', '', raw.strip().upper())

# ══════════════════════════════════════════════════════════════════════════════
# TOOL HANDLERS  — called by AgentRegistry.call_tool()
# ══════════════════════════════════════════════════════════════════════════════

def get_flight_info(flight_number: str) -> dict:
    """MCP tool: get_flight_info"""
    fn = _sanitise(flight_number)
    conn = None
    try:
        conn = _get_connection()
        row  = conn.execute(_SELECT_FLIGHT_SQL, (fn,)).fetchone()
    finally:
        if conn: conn.close()

    if row is None:
        return {"agent":"flight_info","tool":"get_flight_info",
                "error": f"Flight '{fn}' not found. Run setup_db.py to seed data."}
    return {
        "agent":            "flight_info",
        "agent_name":       "Flight Operations Agent",
        "tool":             "get_flight_info",
        "flight_number":    row["flight_number"],
        "airline":          row["airline"],
        "origin":           row["origin"],
        "origin_code":      row["origin_code"],
        "destination":      row["destination"],
        "destination_code": row["destination_code"],
        "departure_time":   row["departure_time"],
        "arrival_time":     row["arrival_time"],
        "aircraft":         row["aircraft"],
        "status":           row["status"],
    }

def list_all_flights() -> dict:
    """MCP tool: list_all_flights"""
    conn = None
    try:
        conn = _get_connection()
        rows = conn.execute(_SELECT_ALL_SQL).fetchall()
    finally:
        if conn: conn.close()
    return {"agent":"flight_info","tool":"list_all_flights","flights":[dict(r) for r in rows]}

if __name__ == "__main__":
    print("=== Agent 2 TOOL_DESCRIPTORS (listTools payload) ===")
    print(json.dumps(TOOL_DESCRIPTORS, indent=2))
    print("\n=== Sample: get_flight_info('QR 120') ===")
    print(json.dumps(get_flight_info("QR 120"), indent=2))
