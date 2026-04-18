"""
================================================================================
AGENT 1 — DESTINATION INTELLIGENCE AGENT
================================================================================
MCP Protocol Compliance
-----------------------
This agent exposes its capabilities via the module-level TOOL_DESCRIPTORS list.
The AgentRegistry reads this list to populate the MCP tools/list catalogue.
The Router calls registry.list_tools() to DISCOVER available tools at runtime,
then calls registry.call_tool(name, args) to dispatch — no hardcoding anywhere.
================================================================================
"""
import json

# ── MCP Tool Descriptor ───────────────────────────────────────────────────────
# AgentRegistry reads TOOL_DESCRIPTORS from every registered agent module.
# This is the MCP "listTools" contract: each entry maps to one callable tool.
TOOL_DESCRIPTORS: list[dict] = [
    {
        "name": "get_destination_intel",
        "description": (
            "Returns destination intelligence for a city: local currency with "
            "USD exchange rate, current weather conditions, and visa requirements "
            "specifically annotated for cabin crew. Use when the user asks about "
            "a city, country, weather, currency, or visa requirements."
        ),
        "agent_module": "agent1_destination",
        "handler":      "get_destination_intel",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city_name": {
                    "type":        "string",
                    "description": "City name to look up (e.g. 'London', 'Dubai', 'Tokyo')"
                }
            },
            "required": ["city_name"]
        },
        "triggers": [
            "details", "currency", "weather", "visa", "timezone",
            "destination", "city", "country", "tell me about", "info about"
        ]
    }
]

#Normally destination data should be fetched from an API, but we'll hardcode some static data for this demo.
# ══════════════════════════════════════════════════════════════════════════════
# STATIC DATA
# ══════════════════════════════════════════════════════════════════════════════
DESTINATION_DATA: dict = {
    "london":     {"city":"London","country":"United Kingdom","code":"GB","currency":{"name":"British Pound Sterling","code":"GBP","symbol":"£","rate_from_usd":0.79},"visa":{"required":True,"type":"UK Standard Visitor Visa","duration":"Up to 6 months","processing":"3 weeks","notes":"Cabin crew on duty may use Crew Visa (C-VISA). EASA-licensed crew may benefit from simplified entry."},"timezone":"GMT/BST (UTC+0 / UTC+1)","language":"English","airport":"London Heathrow (LHR)"},
    "new york":   {"city":"New York","country":"United States","code":"US","currency":{"name":"US Dollar","code":"USD","symbol":"$","rate_from_usd":1.0},"visa":{"required":True,"type":"C-1/D Crewmember / Transit Visa","duration":"Up to 29 days per stay","processing":"2–4 weeks","notes":"Airline crew must hold a C-1/D visa. B-1/B-2 is NOT accepted for crew duties."},"timezone":"EST/EDT (UTC-5 / UTC-4)","language":"English","airport":"John F. Kennedy International (JFK)"},
    "paris":      {"city":"Paris","country":"France","code":"FR","currency":{"name":"Euro","code":"EUR","symbol":"€","rate_from_usd":0.92},"visa":{"required":True,"type":"Schengen Visa / Crew Visa","duration":"90 days within 180-day period","processing":"2 weeks","notes":"Crew on duty exempt with valid crew ID and flight documents."},"timezone":"CET/CEST (UTC+1 / UTC+2)","language":"French","airport":"Paris Charles de Gaulle (CDG)"},
    "dubai":      {"city":"Dubai","country":"United Arab Emirates","code":"AE","currency":{"name":"UAE Dirham","code":"AED","symbol":"د.إ","rate_from_usd":3.67},"visa":{"required":False,"type":"Visa on Arrival / Crew Exemption","duration":"30 days (tourist)","processing":"On arrival","notes":"Most nationalities receive visa on arrival. Active crew are exempt."},"timezone":"GST (UTC+4)","language":"Arabic / English widely spoken","airport":"Dubai International (DXB)"},
    "doha":       {"city":"Doha","country":"Qatar","code":"QA","currency":{"name":"Qatari Riyal","code":"QAR","symbol":"﷼","rate_from_usd":3.64},"visa":{"required":False,"type":"Visa Free / Crew Exemption","duration":"30 days","processing":"On arrival","notes":"Over 80 nationalities are visa-free. Crew on duty exempt with airline credentials."},"timezone":"AST (UTC+3)","language":"Arabic / English widely spoken","airport":"Hamad International (DOH)"},
    "singapore":  {"city":"Singapore","country":"Singapore","code":"SG","currency":{"name":"Singapore Dollar","code":"SGD","symbol":"S$","rate_from_usd":1.34},"visa":{"required":False,"type":"Visa Free (most countries)","duration":"30–90 days","processing":"N/A","notes":"Most nationalities enter visa-free. Crew may use a Crew Pass."},"timezone":"SGT (UTC+8)","language":"English / Malay / Mandarin / Tamil","airport":"Singapore Changi (SIN)"},
    "sydney":     {"city":"Sydney","country":"Australia","code":"AU","currency":{"name":"Australian Dollar","code":"AUD","symbol":"A$","rate_from_usd":1.53},"visa":{"required":True,"type":"ETA / Crew Travel Authority (CTA)","duration":"Up to 12 months","processing":"Instant to 24 h","notes":"Active crew must hold a CTA granted by the airline's AOC holder."},"timezone":"AEST/AEDT (UTC+10 / UTC+11)","language":"English","airport":"Sydney Kingsford Smith (SYD)"},
    "tokyo":      {"city":"Tokyo","country":"Japan","code":"JP","currency":{"name":"Japanese Yen","code":"JPY","symbol":"¥","rate_from_usd":149.50},"visa":{"required":True,"type":"Tourist Visa / Crew Short-Stay Exemption","duration":"15–90 days","processing":"5–10 working days","notes":"Crew on duty may transit without a visa. Short-stay exemptions for select nationalities."},"timezone":"JST (UTC+9)","language":"Japanese","airport":"Tokyo Narita (NRT) / Haneda (HND)"},
    "mumbai":     {"city":"Mumbai","country":"India","code":"IN","currency":{"name":"Indian Rupee","code":"INR","symbol":"₹","rate_from_usd":83.12},"visa":{"required":True,"type":"e-Visa / Regular Visa","duration":"30–180 days","processing":"3–5 business days","notes":"e-Visa available for most nationalities. Crew on duty exempt with valid crew documents."},"timezone":"IST (UTC+5:30)","language":"Hindi / English / Marathi","airport":"Chhatrapati Shivaji Maharaj International (BOM)"},
}

#Normally weather data should be fetched from an API, but we'll hardcode some static data for this demo.
WEATHER_DATA: dict = {
    "london":    {"temp":"12°C / 54°F","condition":"Overcast with light drizzle","humidity":"78%","wind":"18 km/h WSW","visibility":"8 km","icon":"🌧️"},
    "new york":  {"temp":"18°C / 64°F","condition":"Partly cloudy","humidity":"62%","wind":"14 km/h NW","visibility":"14 km","icon":"⛅"},
    "paris":     {"temp":"15°C / 59°F","condition":"Mostly sunny","humidity":"55%","wind":"10 km/h NE","visibility":"20 km","icon":"🌤️"},
    "dubai":     {"temp":"38°C / 100°F","condition":"Sunny and hazy","humidity":"45%","wind":"20 km/h NW","visibility":"10 km","icon":"☀️"},
    "doha":      {"temp":"36°C / 97°F","condition":"Sunny","humidity":"42%","wind":"15 km/h N","visibility":"12 km","icon":"☀️"},
    "singapore": {"temp":"29°C / 84°F","condition":"Thundershowers likely","humidity":"85%","wind":"22 km/h SE","visibility":"6 km","icon":"⛈️"},
    "sydney":    {"temp":"22°C / 72°F","condition":"Clear skies","humidity":"60%","wind":"12 km/h E","visibility":"25 km","icon":"🌞"},
    "tokyo":     {"temp":"20°C / 68°F","condition":"Cherry blossom season, fair","humidity":"65%","wind":"8 km/h SW","visibility":"18 km","icon":"🌸"},
    "mumbai":    {"temp":"32°C / 90°F","condition":"Hot and humid","humidity":"80%","wind":"25 km/h SW","visibility":"7 km","icon":"🌡️"},
}

# ── Helpers ───────────────────────────────────────────────────────────────────
def _normalise(text: str) -> str:
    return text.lower().strip()

def _fuzzy_match(key: str) -> str | None:
    for k in DESTINATION_DATA:
        if k in key or key in k:
            return k
    return None

# ══════════════════════════════════════════════════════════════════════════════
# TOOL HANDLER  — called by AgentRegistry.call_tool()
# ══════════════════════════════════════════════════════════════════════════════
def get_destination_intel(city_name: str) -> dict:
    """MCP tool: get_destination_intel"""
    key     = _normalise(city_name)
    dest    = DESTINATION_DATA.get(key)
    weather = WEATHER_DATA.get(key)
    if dest is None:
        mk = _fuzzy_match(key)
        if mk:
            dest    = DESTINATION_DATA[mk]
            weather = WEATHER_DATA.get(mk)
    if dest is None:
        return {"agent":"destination_intel","tool":"get_destination_intel",
                "error": f"Destination '{city_name}' not found. Supported: {', '.join(DESTINATION_DATA)}"}
    return {
        "agent":      "destination_intel",
        "agent_name": "Destination Intelligence Agent",
        "tool":       "get_destination_intel",
        "city":       dest["city"],
        "country":    dest["country"],
        "airport":    dest["airport"],
        "timezone":   dest["timezone"],
        "language":   dest["language"],
        "currency":   dest["currency"],
        "visa":       dest["visa"],
        "weather":    weather or {"condition":"Data unavailable","icon":"❓"},
    }

if __name__ == "__main__":
    print("=== Agent 1 TOOL_DESCRIPTORS (listTools payload) ===")
    print(json.dumps(TOOL_DESCRIPTORS, indent=2))
    print("\n=== Sample invocation ===")
    print(json.dumps(get_destination_intel("London"), indent=2, ensure_ascii=False))
