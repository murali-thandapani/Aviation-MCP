"""
================================================================================
AGENT REGISTRY  —  MCP tools/list Discovery Engine
================================================================================
File        : agent_registry.py

This is the heart of the MCP protocol implementation.

The MCP listTools Contract
---------------------------
In the official MCP specification, a server must respond to:

    {"jsonrpc":"2.0","id":1,"method":"tools/list"}

with a list of ToolDefinition objects:

    {
      "tools": [
        {
          "name":        "get_destination_intel",
          "description": "Returns currency, weather and visa info for a city...",
          "inputSchema": { "type": "object", "properties": { ... } }
        },
        {
          "name":        "get_flight_info",
          "description": "Retrieves flight schedule from the local database...",
          "inputSchema": { "type": "object", "properties": { ... } }
        }
      ]
    }

The client then decides WHICH tool to call based on the descriptions and the
user's intent — no hardcoding on the client side.

How AgentRegistry Implements This
-----------------------------------
1. REGISTRATION
   At startup, the server calls registry.register(module_name) for each agent.
   The registry imports the module and reads its TOOL_DESCRIPTORS list.
   Each descriptor is stored in an internal catalogue keyed by tool name.

2. DISCOVERY  (tools/list equivalent)
   registry.list_tools() returns the full catalogue — the same payload that
   MCP's tools/list method would return.  The router calls this to find
   candidate tools for a prompt.

3. TOOL SELECTION  (done by router using the catalogue)
   The router scores each tool by matching the prompt against:
     - trigger keywords  (from the tool descriptor)
     - flight-number regex  (special pattern for Agent 2)
     - city name substring  (for Agent 1)
   The highest-scoring tool wins.

4. DISPATCH  (tools/call equivalent)
   registry.call_tool(tool_name, arguments) looks up the tool in the
   catalogue, imports the handler module, and calls the handler function
   with the provided arguments dict.  No agent module names live in the router.

5. INTROSPECTION
   registry.get_tool(name) — returns a single tool descriptor
   registry.tool_names()   — returns list of registered tool names
   registry.summary()      — returns a compact registration report

Design Benefits
---------------
  • Adding a new agent = creating a new .py file with TOOL_DESCRIPTORS.
    Zero changes to router_agent.py or mcp_server.py.
  • Tools are discovered at runtime, not compiled in.
  • The registry is the single source of truth for what the system can do.
  • Fully testable in isolation: registry.list_tools() can be called without
    starting the HTTP server.

Libraries Used
--------------
  importlib  (stdlib)
    importlib.import_module(name) dynamically imports a Python module by name
    string at runtime.  This is how the registry loads agent modules without
    knowing their names at write time.  Alternative: __import__() is the
    lower-level version; importlib is the modern, recommended API.

  inspect    (stdlib)
    inspect.getmembers(module, predicate) lists all attributes of a module
    matching a filter.  Used to verify that handler functions exist on the
    module before registering them.  Prevents silent failures at dispatch time.

  logging    (stdlib)
    Structured logging replaces print() statements for operational visibility.
    log.info() messages go to stdout in development; can be directed to a
    log aggregator (Datadog, CloudWatch) in production by changing the handler.
================================================================================
"""

import importlib   # Dynamic module loading by name string — core of discovery
import inspect     # Introspect module attributes to validate handler names
import logging     # Structured logging for registration events
from typing import Any

# ── Logger ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level  = logging.INFO,
    format = "[%(levelname)s] %(name)s — %(message)s"
)
log = logging.getLogger("AgentRegistry")


# ══════════════════════════════════════════════════════════════════════════════
# REGISTRY CLASS
# ══════════════════════════════════════════════════════════════════════════════

class AgentRegistry:
    """
    Dynamic MCP tool registry.

    Lifecycle
    ---------
    1. Instantiate:    registry = AgentRegistry()
    2. Register agents: registry.register("agent1_destination")
                        registry.register("agent2_flight")
    3. Discover tools: tools = registry.list_tools()   # → tools/list payload
    4. Dispatch:       result = registry.call_tool("get_flight_info",
                                                   {"flight_number": "QR120"})
    """

    def __init__(self):
        # _catalogue: maps tool_name (str) → full descriptor dict
        # The descriptor also carries a reference to the loaded module object
        # so dispatch doesn't need to re-import.
        self._catalogue: dict[str, dict] = {}
        log.info("AgentRegistry initialised (empty)")

    # ── Registration ─────────────────────────────────────────────────────────

    def register(self, module_name: str) -> int:
        """
        Import a Python module and read its TOOL_DESCRIPTORS into the catalogue.

        This is the listTools population step.  Each agent module must define:

            TOOL_DESCRIPTORS: list[dict]

        where each dict has at minimum: name, description, handler, inputSchema.

        Parameters
        ----------
        module_name : str
            Python module name to import (e.g. "agent1_destination").
            Must be importable from sys.path.

        Returns
        -------
        int
            Number of tools registered from this module.

        Raises
        ------
        ImportError    — module not found or has a syntax error
        AttributeError — module has no TOOL_DESCRIPTORS attribute
        ValueError     — a descriptor is missing required keys
        """
        log.info(f"Registering module: {module_name}")

        # importlib.import_module: the MCP-compliant way to load agents
        # dynamically.  If we used a direct `import agent1_destination` here,
        # adding a third agent would require editing this file.  With importlib,
        # the registry is fully data-driven.
        module = importlib.import_module(module_name)

        if not hasattr(module, "TOOL_DESCRIPTORS"):
            raise AttributeError(
                f"Module '{module_name}' does not define TOOL_DESCRIPTORS. "
                "Every agent module must expose a TOOL_DESCRIPTORS list to "
                "participate in MCP tool discovery."
            )

        descriptors = module.TOOL_DESCRIPTORS
        registered  = 0

        for descriptor in descriptors:
            # Validate required fields
            required_keys = {"name", "description", "handler", "inputSchema"}
            missing = required_keys - set(descriptor.keys())
            if missing:
                raise ValueError(
                    f"Tool descriptor in '{module_name}' is missing keys: {missing}"
                )

            tool_name    = descriptor["name"]
            handler_name = descriptor["handler"]

            # Validate that the handler function actually exists on the module
            # inspect.getattr_static avoids triggering descriptors/properties
            if not hasattr(module, handler_name):
                raise AttributeError(
                    f"Handler '{handler_name}' declared in TOOL_DESCRIPTORS "
                    f"does not exist on module '{module_name}'."
                )

            handler_fn = getattr(module, handler_name)
            if not callable(handler_fn):
                raise TypeError(
                    f"'{handler_name}' on module '{module_name}' is not callable."
                )

            # Store the descriptor + resolved references in the catalogue
            self._catalogue[tool_name] = {
                **descriptor,              # original descriptor fields
                "_module":  module,        # resolved module object (avoids re-import)
                "_handler": handler_fn,    # resolved callable (avoids getattr at call time)
            }

            log.info(f"  ✓ Tool registered: '{tool_name}' → {module_name}.{handler_name}()")
            registered += 1

        return registered

    # ── Discovery (tools/list) ────────────────────────────────────────────────

    def list_tools(self) -> list[dict]:
        """
        Return the MCP tools/list payload.

        This is the exact equivalent of the MCP protocol's tools/list method.
        The returned list contains one entry per registered tool, with the
        fields defined in the MCP ToolDefinition schema:

            name        — unique tool identifier
            description — human/LLM-readable description
            inputSchema — JSON Schema for accepted arguments
            triggers    — keyword hints used by the router for scoring
            agent_module— which agent module owns this tool

        Internal fields (_module, _handler) are stripped from the output.

        Returns
        -------
        list[dict]
            Sorted by tool name for deterministic output.
        """
        public_fields = {"name", "description", "inputSchema", "triggers",
                         "agent_module", "handler"}
        return [
            {k: v for k, v in descriptor.items() if k in public_fields}
            for descriptor in sorted(self._catalogue.values(), key=lambda d: d["name"])
        ]

    # ── Single tool lookup ────────────────────────────────────────────────────

    def get_tool(self, tool_name: str) -> dict | None:
        """
        Return the public descriptor for a single tool, or None if not found.
        """
        d = self._catalogue.get(tool_name)
        if d is None:
            return None
        public_fields = {"name", "description", "inputSchema", "triggers", "agent_module", "handler"}
        return {k: v for k, v in d.items() if k in public_fields}

    # ── Dispatch (tools/call) ─────────────────────────────────────────────────

    def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """
        Invoke a registered tool by name with the given arguments.

        This is the MCP tools/call equivalent.  The router calls this after
        determining which tool best matches the user's prompt via list_tools().

        Parameters
        ----------
        tool_name : str
            The tool name as declared in TOOL_DESCRIPTORS["name"].
        arguments : dict
            Keyword arguments to pass to the handler function.
            Must match the tool's inputSchema.

        Returns
        -------
        dict
            The tool handler's return value.

        Raises
        ------
        KeyError   — tool_name not in catalogue (unregistered tool)
        TypeError  — arguments do not match the handler signature
        """
        if tool_name not in self._catalogue:
            registered = list(self._catalogue.keys())
            raise KeyError(
                f"Tool '{tool_name}' is not registered. "
                f"Registered tools: {registered}"
            )

        descriptor = self._catalogue[tool_name]
        handler_fn = descriptor["_handler"]

        log.info(f"Dispatching tool: '{tool_name}' with args: {list(arguments.keys())}")

        # Call the handler — **arguments unpacks the dict as keyword args
        # e.g. handler_fn(city_name="London") or handler_fn(flight_number="QR120")
        return handler_fn(**arguments)

    # ── Introspection helpers ─────────────────────────────────────────────────

    def tool_names(self) -> list[str]:
        """Return a sorted list of all registered tool names."""
        return sorted(self._catalogue.keys())

    def __len__(self) -> int:
        return len(self._catalogue)

    def __contains__(self, tool_name: str) -> bool:
        return tool_name in self._catalogue

    def summary(self) -> str:
        """Return a human-readable registration report."""
        lines = [f"AgentRegistry — {len(self._catalogue)} tool(s) registered:"]
        for name, d in sorted(self._catalogue.items()):
            lines.append(
                f"  [{d['agent_module']}] {name} "
                f"→ handler: {d['handler']}()"
            )
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# MODULE-LEVEL SINGLETON
# ──────────────────────────────────────────────────────────────────────────────
# A single registry instance is created here and imported by mcp_server.py
# and router_agent.py.  This avoids passing the registry as a parameter
# through the call stack while ensuring there is exactly one catalogue per
# process.
#
# Why not a class with @staticmethod?
#   A singleton instance is simpler to mock in tests and allows subclassing
#   (e.g. TestRegistry that loads mock agents) without metaclass tricks.
# ══════════════════════════════════════════════════════════════════════════════

registry = AgentRegistry()


# ── Standalone demo ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json

    # Register all agents
    registry.register("agent1_destination")
    registry.register("agent2_flight")

    print("\n" + registry.summary())

    print("\n=== tools/list payload ===")
    tools = registry.list_tools()
    for t in tools:
        print(f"\n  Tool : {t['name']}")
        print(f"  Agent: {t['agent_module']}")
        print(f"  Desc : {t['description'][:80]}...")
        print(f"  Schema: {json.dumps(t['inputSchema'])}")

    print("\n=== tools/call: get_destination_intel(city_name='Dubai') ===")
    result = registry.call_tool("get_destination_intel", {"city_name": "Dubai"})
    print(json.dumps(result, indent=2, ensure_ascii=False))

    print("\n=== tools/call: get_flight_info(flight_number='QR 120') ===")
    result = registry.call_tool("get_flight_info", {"flight_number": "QR 120"})
    print(json.dumps(result, indent=2, ensure_ascii=False))
