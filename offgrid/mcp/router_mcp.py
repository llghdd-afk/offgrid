"""
KaiwuMCP: Router MCP server.
CORE-7: This is the ONLY external entry point. LLM does not directly see experts.
Single tool: offgrid_execute(task_description: str) -> str

The `mcp` package is optional. This module is always importable, but
starting the server requires `pip install mcp`.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False


def _require_mcp():
    if not _MCP_AVAILABLE:
        raise RuntimeError(
            "MCP package not installed. Install with: pip install mcp\n"
            "KaiwuMCP requires the 'mcp' package to run as an MCP server."
        )


class KaiwuMCP:
    """MCP server that wraps the entire KwCode pipeline as a single tool."""

    def __init__(self, gate, orchestrator, memory, project_root: str):
        _require_mcp()
        self.gate = gate
        self.orchestrator = orchestrator
        self.memory = memory
        self.project_root = project_root
        self.server = Server("offgrid")
        self._setup_tools()

    def _setup_tools(self):
        """Register the single offgrid_execute tool."""

        @self.server.list_tools()
        async def list_tools():
            return [
                Tool(
                    name="offgrid_execute",
                    description=(
                        "Execute a coding task through KwCode's local-model expert pipeline. "
                        "KwCode automatically selects the right expert, locates relevant files, "
                        "generates patches, and verifies the result."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "task_description": {
                                "type": "string",
                                "description": "Natural language description of the coding task.",
                            }
                        },
                        "required": ["task_description"],
                    },
                )
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict):
            if name != "offgrid_execute":
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

            if not isinstance(arguments, dict):
                return [TextContent(type="text", text="Error: arguments must be a JSON object.")]

            task_raw = arguments.get("task_description", "")
            task = str(task_raw).strip() if task_raw else ""
            if not task:
                return [TextContent(type="text", text="Error: task_description is required.")]

            try:
                result_text = await self._execute(task)
                return [TextContent(type="text", text=result_text)]
            except Exception as e:
                logger.exception("offgrid_execute failed")
                return [TextContent(type="text", text=f"Error: {e}")]

    async def _execute(self, task: str) -> str:
        """Run the full pipeline for a task. Returns summary text."""
        loop = asyncio.get_event_loop()

        def _run():
            memory_ctx = self.memory.load(self.project_root)
            gate_result = self.gate.classify(task, memory_context=memory_ctx)

            result = self.orchestrator.run(
                user_input=task,
                gate_result=gate_result,
                project_root=self.project_root,
            )
            return result

        result = await loop.run_in_executor(None, _run)

        if result["success"]:
            ctx = result["context"]
            files = []
            if ctx.locator_output:
                files = ctx.locator_output.get("relevant_files", [])
            elif ctx.generator_output:
                files = [p.get("file", "") for p in ctx.generator_output.get("patches", [])]

            explanation = ""
            if ctx.generator_output:
                explanation = ctx.generator_output.get("explanation", "")

            elapsed = result.get("elapsed", 0)
            parts = [f"Done ({elapsed:.1f}s)"]
            if files:
                parts.append(f"Files: {', '.join(files[:10])}")
            if explanation:
                parts.append(explanation[:500])
            return "\n".join(parts)
        else:
            error = result.get("error", "Unknown error")
            return f"Failed: {error}"

    async def run_stdio(self):
        """Run MCP server over stdio."""
        _require_mcp()
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(read_stream, write_stream, self.server.create_initialization_options())
