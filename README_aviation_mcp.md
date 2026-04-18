# ✈️ Aviation MCP — Multi-Agent System

> A Python multi-agent backend implementing the Model Context Protocol (MCP / JSON-RPC 2.0) for aviation operations — with dynamic tool discovery, a standalone HTML frontend, and zero hardcoded routing.

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.1-black?logo=flask&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-3-blue?logo=sqlite&logoColor=white)
![MCP](https://img.shields.io/badge/Protocol-MCP%20%2F%20JSON--RPC%202.0-purple)
![License](https://img.shields.io/badge/license-MIT-brightgreen)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)

---

## 📌 Overview

The Aviation MCP System is a production-grade multi-agent backend that answers two categories of aviation query through a standards-compliant MCP interface:

- **Destination Intelligence** — currency, live weather, and visa requirements for cabin crew
- **Flight Operations** — schedule, route, aircraft, and status from a local SQLite database

The system uses `tools/list` to discover agents at runtime and `tools/call` to dispatch — no hardcoded routing, no if/else chains per agent. Adding a new agent requires creating one Python file.

---

## 🎯 Features

- **MCP Protocol compliant** — `POST /mcp/tools/list` and `POST /mcp/tools/call` with JSON-RPC 2.0 envelopes
- **Dynamic AgentRegistry** — agents register themselves via `TOOL_DESCRIPTORS`; router discovers them at runtime via `importlib`
- **Tool scoring engine** — +10 per keyword hit, +20 city detected, +30 flight number detected
- **Full routing audit trail** — every response includes tool scores, reasons, and arguments passed
- **SQLite flight database** — 17 pre-seeded flights across 6 airlines (Qatar Airways, Emirates, British Airways, Singapore Airlines, Air India)
- **9 destination cities** — London, New York, Paris, Dubai, Doha, Singapore, Sydney, Tokyo, Mumbai
- **Standalone HTML frontend** — opens directly from the filesystem (`file://`) with no build step
- **CORS / file:// support** — custom `@app.after_request` hook handles `Origin: null` from local HTML files
- **REST + MCP endpoints** — both natural-language query and direct tool call APIs available

---

## 🏗️ Architecture

```
User Prompt  (natural language)
      │
      ▼
POST /api/query  →  mcp_server.py (Flask)
      │
      ▼
router_agent.py
      │
      ├── registry.list_tools()     ← MCP tools/list
      │        └── returns all 3 registered tool descriptors
      │
      ├── _detect_city()            ← substring match on CITY_NAMES
      ├── _detect_flight()          ← regex [A-Za-z]{2,3}[0-9]{1,4}
      │
      ├── _score_tools()            ← +10 keyword / +20 city / +30 flight#
      │
      └── registry.call_tool()      ← MCP tools/call
               │
               ├── Agent 1: get_destination_intel()  → dict lookup
               └── Agent 2: get_flight_info()        → SQLite SELECT
```

---

## 🛠️ Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| HTTP server | Flask 3.1 | REST + MCP endpoints |
| Cross-origin | Flask-CORS 6.0 | Browser frontend access |
| Agent discovery | `importlib` | Dynamic module loading |
| Flight database | SQLite 3 | Embedded flight records |
| Routing | `re` (regex) | IATA flight number detection |
| Frontend | Vanilla HTML/JS | Standalone UI, no build step |

---

## 📡 API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/mcp/tools/list` | MCP tools/list — discover all registered tools |
| `POST` | `/mcp/tools/call` | MCP tools/call — invoke a tool directly by name |
| `POST` | `/api/query` | Natural-language routing (uses listTools internally) |
| `GET` | `/api/health` | Liveness probe — registered tools + DB path |
| `GET` | `/api/flights` | List all flights in the database |
| `GET` | `/api/destinations` | List all supported destination cities |

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10 or later
- pip

### Installation

```bash
# Clone the repository
git clone https://github.com/murali-thandapani/aviation-mcp
cd aviation-mcp/agents

# Install dependencies
pip install -r requirements.txt

# Seed the SQLite database (run once)
python setup_db.py

# Start the server
python mcp_server.py
```

Expected startup output:
```
[REGISTRY] Registered 'agent1_destination' — 1 tool(s)
[REGISTRY] Registered 'agent2_flight' — 2 tool(s)
 * Running on http://127.0.0.1:5050
```

### Using the Frontend

Double-click `index.html` — it opens in any browser as a `file://` URL. The amber banner at the top lets you confirm the API base URL (`http://127.0.0.1:5050`) and connect. No web server needed for the frontend.

---

## 💬 Sample Queries

```bash
# Destination query
curl -X POST http://127.0.0.1:5050/api/query \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Provide London details"}'

# Flight query
curl -X POST http://127.0.0.1:5050/api/query \
  -H "Content-Type: application/json" \
  -d '{"prompt": "provide QR 120 details"}'

# Direct MCP tools/list call
curl -X POST http://127.0.0.1:5050/mcp/tools/list \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

| Prompt | Routes To | Returns |
|--------|-----------|---------|
| `Provide London details` | Agent 1 | GBP currency, weather, UK visa (C-VISA for crew) |
| `provide QR 120 details` | Agent 2 | DOH→LHR, 02:35→07:50, Boeing 777-300ER, On Time |
| `Provide Dubai details` | Agent 1 | AED currency, weather, visa exempt for active crew |
| `provide EK201 details` | Agent 2 | DXB→LHR, 08:30→13:10, Airbus A380, On Time |

---

## 📁 Project Structure

```
aviation-mcp/
├── agents/
│   ├── mcp_server.py           # Entry point — Flask HTTP gateway
│   ├── agent_registry.py       # MCP discovery engine (listTools + call)
│   ├── router_agent.py         # Prompt scoring and dispatch
│   ├── agent1_destination.py   # Destination Intelligence Agent
│   ├── agent2_flight.py        # Flight Operations Agent
│   ├── setup_db.py             # SQLite seed script
│   ├── flights.db              # SQLite database (created by setup_db.py)
│   └── requirements.txt
├── index.html                  # Standalone frontend (file:// compatible)
└── README.md
```

---

## 🧩 Adding a New Agent

1. Create `agents/agent3_yourname.py` with a `TOOL_DESCRIPTORS` list and handler function
2. Add one line to `mcp_server.py`:

```python
AGENT_MODULES = ["agent1_destination", "agent2_flight", "agent3_yourname"]
```

No changes needed to `router_agent.py` or `agent_registry.py`. The new tool is automatically included in `tools/list` and eligible for scoring.

---

## ✈️ Flights in Database

| Airline | Flights |
|---------|---------|
| Qatar Airways | QR120, QR007, QR305, QR948, QR570, QR528 |
| Emirates | EK201, EK505, EK432, EK407 |
| British Airways | BA105, BA007, BA011 |
| Singapore Airlines | SQ321, SQ25 |
| Air India | AI101, AI144 |

---

## 🗺️ Roadmap

- [ ] Agent 3: NOTAM (Notice to Airmen) lookup
- [ ] Live weather via OpenWeatherMap API
- [ ] Live flight status via AviationStack API
- [ ] PostgreSQL migration for production deployments
- [ ] Authentication layer for multi-user deployments

---

## 👤 Author

**Murali Thandapani**
- GitHub: [@murali-thandapani](https://github.com/murali-thandapani)
- LinkedIn: [linkedin.com/in/murali-thandapani](https://linkedin.com/in/murali-thandapani)

---

## 📄 License

MIT License — free to use, modify, and distribute.
