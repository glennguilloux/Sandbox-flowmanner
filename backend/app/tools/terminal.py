import subprocess

from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

ALLOWED_COMMANDS = {
    "ls",
    "pwd",
    "echo",
    "cat",
    "head",
    "tail",
    "grep",
    "find",
    "wc",
    "date",
    "whoami",
    "uname",
    "df",
    "du",
    "ps",
    "top",
    "env",
    "which",
}
TIMEOUT_SECONDS = 10


class TerminalInput(ToolInput):
    command: str = Field(..., description="Shell command to execute")
    working_dir: str = Field("/tmp", description="Working directory for execution")


class TerminalTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="terminal_exec",
            name="Terminal Execute",
            description="Execute a shell command and return stdout/stderr",
            category="terminal",
            input_schema=TerminalInput.schema_extra(),
            tags=["shell", "exec", "command"],
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = TerminalInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        command = validated.command.strip()
        if not command:
            return ToolResult.error_result(tool_id=self.tool_id, error="Empty command")

        parts = command.split()
        base_cmd = parts[0]

        if base_cmd not in ALLOWED_COMMANDS:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Command '{base_cmd}' not in allowlist. Allowed: {sorted(ALLOWED_COMMANDS)}",
            )

        working_dir = validated.working_dir or "/tmp"

        try:
            proc = subprocess.run(
                parts,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                cwd=working_dir,
            )
            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "exit_code": proc.returncode,
                    "command": command,
                },
            )
        except subprocess.TimeoutExpired:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Command timed out after {TIMEOUT_SECONDS} seconds",
            )
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


register_tool(TerminalTool())
