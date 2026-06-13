"""ESPHome MCP Server — FastMCP application with streamable HTTP transport."""

import json
import logging
import os
import uvicorn

# Prevent UV from failing package resolution due to Home Assistant wheels index constraints
os.environ["UV_INDEX_STRATEGY"] = "unsafe-best-match"

from mcp.server.fastmcp import FastMCP

from . import tools
from .auth import BearerAuthMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("esphome-mcp")

mcp = FastMCP(
    name="esphome",
    host="0.0.0.0",
    stateless_http=True,
)


# ---------------------------------------------------------------------------
# Register tools
# ---------------------------------------------------------------------------
@mcp.tool()
def esphome_list_devices() -> str:
    """List all available ESPHome device configurations.

    Scans YAML files in the ESPHome config directory,
    returning device names and friendly names.
    """
    return tools.list_devices()


@mcp.tool()
async def esphome_validate(device: str, timeout: int | None = None) -> str:
    """Validate an ESPHome device config.

    Verifies syntax and semantic configuration. Useful to run before esphome_compile or esphome_flash to check for configuration errors.

    IMPORTANT: If you have created or edited the device's configuration file locally in your workspace, you MUST first call esphome_push_files to upload the updated file(s) to the Home Assistant server before running this validation.

    Args:
        device: Device name (e.g. 'statusdisplay') or YAML filename. Use esphome_list_devices to discover available devices.
        timeout: Optional override for the command timeout in seconds.
    """
    return await tools.validate(device, timeout)


@mcp.tool()
async def esphome_compile(device: str, timeout: int | None = None) -> str:
    """Compile ESPHome firmware for a device.

    Compiles the binary. It is recommended to run esphome_validate first to verify syntax.
    Use esphome_flash instead if you want to compile AND upload it to the device.
    Note: Compilations can take several minutes on slower hosts. The AI client can increase the timeout parameter for the initial compilation.

    IMPORTANT: If you have created or edited the device's configuration file locally in your workspace, you MUST first call esphome_push_files to upload the updated file(s) to the Home Assistant server before running this compilation.

    Args:
        device: Device name (e.g. 'statusdisplay') or YAML filename. Use esphome_list_devices to discover available devices.
        timeout: Optional override for the command timeout in seconds.
    """
    return await tools.compile_device(device, timeout)


@mcp.tool()
async def esphome_flash(device: str, port: str = "OTA", timeout: int | None = None) -> str:
    """OTA or serial flash a device.

    Compiles and uploads the firmware. It is recommended to run esphome_validate
    first to verify syntax, and highly recommended to run esphome_logs immediately after
    flashing completes to verify that the device successfully booted and connected to services.

    IMPORTANT: If you have created or edited the device's configuration file locally in your workspace, you MUST first call esphome_push_files to upload the updated file(s) to the Home Assistant server before flashing.

    Args:
        device: Device name (e.g. 'statusdisplay') or YAML filename. Use esphome_list_devices to discover available devices.
        port: The target port/address to use for flashing (e.g. '/dev/ttyUSB0', 'OTA'). Defaults to 'OTA'.
        timeout: Optional override for the command timeout in seconds.
    """
    return await tools.flash(device, port, timeout)


@mcp.tool()
async def esphome_logs(device: str, num_lines: int = 50, duration: int = 5, port: str = "OTA") -> str:
    """Get recent logs from an ESPHome device.

    Captures a snapshot of logs by listening for a specific duration.
    Particularly useful after calling esphome_flash to monitor startup behavior and debug issues.

    Args:
        device: Device name (e.g. 'statusdisplay') or YAML filename. Use esphome_list_devices to discover available devices.
        num_lines: Number of log lines to return (default 50).
        duration: Time in seconds to listen for logs (default 5).
        port: The target port/address to receive logs from (e.g. '/dev/ttyUSB0', 'OTA'). Defaults to 'OTA'.
    """
    return await tools.logs(device, num_lines, duration, port)


@mcp.tool()
def esphome_push_files(files: dict[str, str]) -> str:
    """Push YAML config files to the ESPHome directory on Home Assistant.

    Writes files to /config/esphome/. Rejects secrets.yaml.

    IMPORTANT: The 'files' parameter MUST be a dictionary/object mapping filenames
    to their complete file contents. Do NOT pass a number, count of files, or list of names.

    Args:
        files: A dictionary mapping target filename to its YAML file content.
               Example: {"livingroom.yaml": "esphome:\n  name: livingroom\n..."}
               Use "archive/filename.yaml" as the key to push/update archived configurations.
    """
    return tools.push_files(files)


@mcp.tool()
def esphome_push_file_chunk(filename: str, content: str, append: bool = False) -> str:
    """Push a chunk of content to a YAML config file on Home Assistant.

    Allows transferring large files (e.g., >30KB or >800 lines) in smaller, manageable chunks
    to bypass size and output truncation limits of AI clients.

    To upload a large file:
    1. Explicitly explain to the user in chat that you are pushing the file in chunks due to size limits, explaining that you will use append=False for the first chunk (to create/overwrite the file) and append=True for subsequent chunks.
    2. Call this tool with append=False and the first chunk.
    3. Call this tool with append=True and the subsequent chunks in order, keeping the user updated on progress.

    Args:
        filename: Target YAML filename (e.g. 'livingroom.yaml' or 'archive/livingroom.yaml').
        content: The text content of this chunk.
        append: If True, appends to the file. If False, overwrites/creates the file. Defaults to False.
    """
    return tools.push_file_chunk(filename, content, append)


@mcp.tool()
def esphome_pull_files(filenames: list[str] | None = None) -> str:
    """Pull YAML config files from the ESPHome directory on Home Assistant.

    Returns file contents. Excludes secrets.yaml.

    Args:
        filenames: Optional list of filenames to pull.
                   If omitted, returns all YAML files.
    """
    result = tools.pull_files(filenames)
    return json.dumps(result, indent=2)


@mcp.tool()
def esphome_push_fonts(files: dict[str, str]) -> str:
    """Push font files to the ESPHome fonts directory on Home Assistant.

    IMPORTANT: The 'files' parameter MUST be a dictionary/object mapping font filenames
    to their base64-encoded file contents. Do NOT pass a number, count of files, or list of names.

    Args:
        files: A dictionary mapping font filename to its base64-encoded file content.
               Example: {"font.ttf": "YmFzZTY0IGNvbnRlbnQ="}
    """
    return tools.push_fonts(files)


@mcp.tool()
def esphome_pull_fonts(filenames: list[str] | None = None) -> str:
    """Pull font files from the ESPHome fonts directory on Home Assistant.

    Returns base64-encoded file contents.

    Args:
        filenames: Optional list of font filenames to pull.
                   If omitted, returns all fonts.
    """
    result = tools.pull_fonts(filenames)
    return json.dumps(result, indent=2)

# ---------------------------------------------------------------------------
# ASGI app with auth middleware
# ---------------------------------------------------------------------------
app = mcp.streamable_http_app()
app.add_middleware(BearerAuthMiddleware)


if __name__ == "__main__":
    port = int(os.environ.get("MCP_PORT", "8099"))
    log.info("ESPHome MCP Server starting on port %d", port)
    uvicorn.run(
        "server.main:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
    )
