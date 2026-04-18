"""
================================================================================
ROUTER AGENT  —  MCP-Compliant Prompt Dispatcher
================================================================================
File        : router_agent.py

How Routing Works Now (MCP-compliant)
---------------------------------------
router calls registry.list_tools() to DISCOVER what is available,
scores each tool against the prompt, and dispatches via
registry.call_tool(best_tool_name, arguments).

The router knows NOTHING about agent1_destination or agent2_flight.
It only knows about the AgentRegistry.

Tool Selection Algorithm
-------------------------
Each tool descriptor carries:
  - "triggers"     : list of keyword strings
  - "inputSchema"  : JSON Schema with property descriptions

The router scores each discovered tool by:
  1. Keyword match — does the prompt contain any trigger word?  (+10 per hit)
  2. City detection — is a known city name in the prompt?
     If yes, boost tools whose trigger list includes destination-type keywords (+20)
  3. Flight-number regex — does the prompt contain an IATA flight number?
     If yes, boost tools that accept a "flight_number" input property (+30)

The tool with the highest score wins.  Ties are broken alphabetically.
If all scores are zero, returns an "unknown" error.

This scoring approach means:
  - Adding a new tool with new trigger keywords automatically participates
    in routing without any code changes here.
  - The routing decision is auditable: the response includes the score
    breakdown for every candidate tool.
================================================================================
"""
import re
import json
import logging
from datetime import datetime, timezone

from agent_registry import registry

log = logging.getLogger("RouterAgent")

# ── Flight-number regex (compiled once at import time) ────────────────────────
FLIGHT_PATTERN = re.compile(r'\b([A-Za-z]{2,3})\s*([0-9]{1,4}[A-Za-z]?)\b', re.IGNORECASE)

# ── City vocabulary — loaded from Agent 1 via registry after registration ─────
# Populated in _get_city_names() after agents are registered.
_CITY_NAMES: list[str] = []

def _get_city_names() -> list[str]:
    """
    Derive the city vocabulary from registered tool descriptors.
    Looks for any tool named 'get_destination_intel' and reads its
    inputSchema to find the city property — then falls back to importing
    DESTINATION_DATA directly from the agent module.
    """
    global _CITY_NAMES
    if _CITY_NAMES:
        return _CITY_NAMES
    try:
        import agent1_destination as a1
        _CITY_NAMES = sorted(a1.DESTINATION_DATA.keys(), key=len, reverse=True)
    except ImportError:
        _CITY_NAMES = []
    return _CITY_NAMES


# ══════════════════════════════════════════════════════════════════════════════
# SCORING ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def _score_tools(prompt: str, tools: list[dict]) -> list[dict]:
    """
    Score each tool against the prompt.  Returns tools sorted by score desc.

    Scoring rules:
      +10  per trigger keyword found in the prompt
      +20  if a known city is detected AND the tool handles destinations
      +30  if a flight number is detected AND the tool accepts flight_number
    """
    prompt_lower = prompt.lower()

    # Detect city
    found_city = None
    for city in _get_city_names():
        if city in prompt_lower:
            found_city = city
            break

    # Detect flight number
    fm = FLIGHT_PATTERN.search(prompt)
    found_flight = (fm.group(1).upper() + fm.group(2).upper()) if fm else None

    scored = []
    for tool in tools:
        score         = 0
        score_reasons = []

        # Keyword trigger match
        for kw in tool.get("triggers", []):
            if kw in prompt_lower:
                score += 10
                score_reasons.append(f"keyword:'{kw}'(+10)")

        # City boost
        if found_city:
            props = tool.get("inputSchema", {}).get("properties", {})
            if "city_name" in props:
                score += 20
                score_reasons.append(f"city:'{found_city}'(+20)")

        # Flight-number boost
        if found_flight:
            props = tool.get("inputSchema", {}).get("properties", {})
            if "flight_number" in props:
                score += 30
                score_reasons.append(f"flight:'{found_flight}'(+30)")

        scored.append({
            "tool":    tool,
            "score":   score,
            "reasons": score_reasons,
            "city":    found_city,
            "flight":  found_flight,
        })

    scored.sort(key=lambda x: (-x["score"], x["tool"]["name"]))
    return scored


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ROUTER FUNCTION
# ══════════════════════════════════════════════════════════════════════════════

def process_prompt(prompt: str) -> dict:
    """
    MCP-compliant prompt dispatcher.

    Steps:
    1. Call registry.list_tools()   ← tools/list discovery
    2. Score each tool vs prompt    ← routing decision
    3. Call registry.call_tool()    ← tools/call dispatch
    4. Return augmented response    ← includes routing audit trail
    """
    if not prompt or not prompt.strip():
        return {"agent": "router", "error": "Empty prompt.", "prompt": prompt}

    routed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # ── Step 1: Discover available tools via listTools ────────────────────────
    tools = registry.list_tools()   # ← THE listTools call
    if not tools:
        return {"agent":"router","error":"No tools registered in AgentRegistry.","prompt":prompt}

    # ── Step 2: Score and rank tools ──────────────────────────────────────────
    scored = _score_tools(prompt, tools)
    best   = scored[0]

    # Build audit trail (all tools + their scores)
    scoring_audit = [
        {"tool": s["tool"]["name"], "score": s["score"], "reasons": s["reasons"]}
        for s in scored
    ]

    if best["score"] == 0:
        return {
            "agent":         "router",
            "error":         (
                "No tool matched the prompt. "
                "Try: 'Provide London details'  or  'provide QR 120 details'"
            ),
            "prompt":        prompt,
            "routed_at":     routed_at,
            "tools_checked": [t["name"] for t in tools],
            "scoring":       scoring_audit,
        }

    selected_tool = best["tool"]
    tool_name     = selected_tool["name"]

    # ── Step 3: Build arguments for the winning tool ──────────────────────────
    if tool_name == "get_destination_intel":
        arguments = {"city_name": best["city"].title()}
    elif tool_name == "get_flight_info":
        arguments = {"flight_number": best["flight"]}
    elif tool_name == "list_all_flights":
        arguments = {}
    else:
        # Generic: try to fill required args from scoring context
        required = selected_tool.get("inputSchema", {}).get("required", [])
        arguments = {}
        if "city_name"      in required and best["city"]:   arguments["city_name"]      = best["city"]
        if "flight_number"  in required and best["flight"]: arguments["flight_number"]  = best["flight"]

    # ── Step 4: Dispatch via registry.call_tool() ─────────────────────────────
    try:
        result = registry.call_tool(tool_name, arguments)   # ← THE tools/call dispatch
    except Exception as exc:
        result = {"agent": "router", "error": f"Dispatch error: {exc}"}

    # ── Augment with routing metadata ─────────────────────────────────────────
    result["prompt"]         = prompt
    result["routed_at"]      = routed_at
    result["routing"] = {
        "tools_discovered":  len(tools),
        "selected_tool":     tool_name,
        "selected_score":    best["score"],
        "score_reasons":     best["reasons"],
        "arguments_passed":  arguments,
        "all_tool_scores":   scoring_audit,
    }
    return result


# ── Standalone demo ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Register agents first
    registry.register("agent1_destination")
    registry.register("agent2_flight")

    print(registry.summary())

    print("\n\n=== listTools output (all discovered tools) ===")
    for t in registry.list_tools():
        print(f"  {t['name']:30s} [{t['agent_module']}]")

    prompts = [
        "Provide London details",
        "provide QR 120 details",
        "What's the visa for Tokyo?",
        "EK201 flight info",
        "Tell me about Mumbai currency",
        "I want to go somewhere nice",
    ]

    for p in prompts:
        print(f"\n{'='*65}")
        print(f"PROMPT: {p}")
        result = process_prompt(p)
        r = result.get("routing", {})
        print(f"TOOL  : {r.get('selected_tool','?')}  (score={r.get('selected_score',0)})")
        print(f"REASON: {r.get('score_reasons','')}")
        if "error" in result:
            print(f"ERROR : {result['error']}")
        elif result.get("agent") == "destination_intel":
            d = result
            print(f"CITY  : {d['city']}, {d['country']}")
            print(f"CURR  : {d['currency']['code']} — 1 USD = {d['currency']['rate_from_usd']} {d['currency']['code']}")
            print(f"VISA  : {'Required' if d['visa']['required'] else 'Not Required'} — {d['visa']['type']}")
        elif result.get("agent") == "flight_info":
            print(f"FLIGHT: {result['flight_number']} ({result['airline']})")
            print(f"ROUTE : {result['origin']} ({result['origin_code']}) → {result['destination']} ({result['destination_code']})")
            print(f"TIME  : {result['departure_time']} → {result['arrival_time']}  [{result['status']}]")
