"""
================================================================================
MCP SERVER  —  Flask HTTP Gateway
================================================================================
File        : mcp_server.py

MCP Protocol Endpoints
-----------------------
This server now exposes the FULL MCP protocol surface, not just /api/query:

    POST /mcp/tools/list    ← MCP tools/list  — discover available tools
    POST /mcp/tools/call    ← MCP tools/call  — invoke a specific tool directly
    POST /api/query         ← Convenience: natural-language routing via router
    GET  /api/flights       ← Flight directory
    GET  /api/destinations  ← Destination directory
    GET  /api/health        ← Liveness probe

The /mcp/* endpoints implement the JSON-RPC 2.0 envelope that the official
MCP specification uses.  Any MCP-compliant client can connect to this server
and call tools directly — without going through the router at all.

The /api/query endpoint is a higher-level convenience wrapper that accepts
natural language and uses the router to select and call the right tool.
================================================================================
"""
from flask      import Flask, request, jsonify, render_template
from flask_cors import CORS
import os, sys, json, logging

# ── Registry bootstrap ────────────────────────────────────────────────────────
# Import the singleton registry and register all agent modules.
# This is the ONLY place agent module names appear — the rest of the system
# is fully data-driven through the registry.
from agent_registry import registry

AGENT_MODULES = ["agent1_destination", "agent2_flight"]

for module_name in AGENT_MODULES:
    try:
        n = registry.register(module_name)
        print(f"[REGISTRY] Registered '{module_name}' — {n} tool(s)")
    except Exception as e:
        print(f"[REGISTRY] ERROR registering '{module_name}': {e}", file=sys.stderr)
        sys.exit(1)

# ── Now import router (after registry is populated) ───────────────────────────
from router_agent import process_prompt

from agent1_destination import DESTINATION_DATA
from agent2_flight      import list_all_flights, _DB_PATH

# ── DB check ─────────────────────────────────────────────────────────────────
if not os.path.exists(_DB_PATH):
    print(f"[FATAL] flights.db not found at: {_DB_PATH}. Run setup_db.py first.", file=sys.stderr)
    sys.exit(1)

# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app, origins="*")
logging.basicConfig(level=logging.INFO)

# ── file:// CORS fix ──────────────────────────────────────────────────────────
# Browsers send Origin: null for pages opened from the filesystem (file://).
# flask-cors origins="*" does NOT match the literal string "null".
# This hook detects that case and rewrites the header to "null" explicitly,
# which satisfies the browser's CORS check for local HTML files.
@app.after_request
def allow_file_origin(response):
    origin = request.headers.get("Origin", "")
    if origin == "null":
        response.headers["Access-Control-Allow-Origin"]  = "null"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


# ══════════════════════════════════════════════════════════════════════════════
# MCP PROTOCOL ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/mcp/tools/list', methods=['POST', 'GET'])
def mcp_tools_list():
    """
    MCP tools/list — returns all registered tools and their schemas.

    This is the canonical listTools method.  Clients call this first to
    discover what the server can do, then call tools/call to invoke a tool.

    MCP JSON-RPC envelope (POST body, optional):
        {"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}

    Response:
        {
          "jsonrpc": "2.0",
          "id": 1,
          "result": {
            "tools": [ { "name":..., "description":..., "inputSchema":... }, ... ]
          }
        }
    """
    body    = request.get_json(silent=True) or {}
    req_id  = body.get("id", 1)
    tools   = registry.list_tools()

    # Strip internal fields, keep only MCP-spec fields
    mcp_tools = [
        {
            "name":        t["name"],
            "description": t["description"],
            "inputSchema": t["inputSchema"],
        }
        for t in tools
    ]

    return jsonify({
        "jsonrpc": "2.0",
        "id":      req_id,
        "result":  {
            "tools":            mcp_tools,
            "total_registered": len(mcp_tools),
            "agents":           list({t["agent_module"] for t in tools}),
        }
    }), 200


@app.route('/mcp/tools/call', methods=['POST'])
def mcp_tools_call():
    """
    MCP tools/call — invoke a specific tool by name.

    MCP JSON-RPC envelope (POST body):
        {
          "jsonrpc": "2.0",
          "id":      2,
          "method":  "tools/call",
          "params":  {
            "name":      "get_destination_intel",
            "arguments": {"city_name": "London"}
          }
        }

    Response:
        {
          "jsonrpc": "2.0",
          "id":      2,
          "result":  { ...tool output... }
        }
    """
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"jsonrpc":"2.0","id":None,
                        "error":{"code":-32700,"message":"Parse error: body must be JSON"}}), 400

    req_id    = body.get("id", 1)
    params    = body.get("params", {})
    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    if not tool_name:
        return jsonify({"jsonrpc":"2.0","id":req_id,
                        "error":{"code":-32602,"message":"params.name is required"}}), 400

    if tool_name not in registry:
        return jsonify({"jsonrpc":"2.0","id":req_id,
                        "error":{"code":-32601,
                                 "message":f"Tool '{tool_name}' not found",
                                 "data":{"registered_tools": registry.tool_names()}}}), 404

    try:
        result = registry.call_tool(tool_name, arguments)
        return jsonify({"jsonrpc":"2.0","id":req_id,"result":result}), 200
    except TypeError as e:
        return jsonify({"jsonrpc":"2.0","id":req_id,
                        "error":{"code":-32602,"message":f"Invalid arguments: {e}"}}), 400
    except Exception as e:
        return jsonify({"jsonrpc":"2.0","id":req_id,
                        "error":{"code":-32603,"message":f"Internal error: {e}"}}), 500


# ══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/query', methods=['POST'])
def query():
    """Natural-language query — router selects and calls the right tool."""
    data   = request.get_json(silent=True)
    if not data:
        return jsonify({"error":"Request body must be JSON"}), 415
    prompt = data.get("prompt","").strip()
    if not prompt:
        return jsonify({"error":"Missing 'prompt' field"}), 400
    return jsonify(process_prompt(prompt)), 200

@app.route('/api/flights', methods=['GET'])
def api_flights():
    return jsonify(list_all_flights()), 200

@app.route('/api/destinations', methods=['GET'])
def api_destinations():
    return jsonify(sorted(DESTINATION_DATA.keys())), 200

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        "status":              "ok",
        "registered_tools":    registry.tool_names(),
        "total_tools":         len(registry),
        "db_path":             _DB_PATH,
        "mcp_endpoints": {
            "list_tools": "POST /mcp/tools/list",
            "call_tool":  "POST /mcp/tools/call",
            "query":      "POST /api/query",
        }
    }), 200


if __name__ == '__main__':
    print("\n Aviation MCP Server — MCP Protocol Compliant")
    print(" ─────────────────────────────────────────────────────")
    print(f" {registry.summary()}")
    print(" ─────────────────────────────────────────────────────")
    print(" MCP endpoints:")
    print("   POST /mcp/tools/list   ← listTools discovery")
    print("   POST /mcp/tools/call   ← direct tool invocation")
    print("   POST /api/query        ← natural-language routing")
    print(" ─────────────────────────────────────────────────────\n")
    app.run(host="0.0.0.0", port=5050, debug=False)


# ══════════════════════════════════════════════════════════════════════════════
# ROOT ROUTE — serves the Flask UI
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/', methods=['GET'])
def ui():
    """Serve the Aviation MCP web console at GET /"""
    return render_template('index.html')
