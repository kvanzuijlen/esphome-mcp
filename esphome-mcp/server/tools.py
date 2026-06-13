"""ESPHome MCP tool implementations.

All tools operate locally on the Home Assistant filesystem with strict path resolution.
"""

import asyncio
import base64
import glob
import logging
import os
import yaml

log = logging.getLogger("esphome-mcp")

ESPHOME_DIR = os.environ.get("ESPHOME_DIR", "/config/esphome")
ESPHOME_BIN = "esphome"

COMPILE_TIMEOUT = int(os.environ.get("ESPHOME_COMPILE_TIMEOUT", "300"))
FLASH_TIMEOUT = int(os.environ.get("ESPHOME_FLASH_TIMEOUT", "600"))
VALIDATE_TIMEOUT = int(os.environ.get("ESPHOME_VALIDATE_TIMEOUT", "120"))

FORBIDDEN_FILES = {"secrets.yaml", ".secret.yaml"}


class SecretLoader(yaml.SafeLoader):
    pass


def secret_constructor(loader, node):
    return f"!secret {loader.construct_scalar(node)}"


def catch_all_constructor(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    elif isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)


SecretLoader.add_constructor("!secret", secret_constructor)
SecretLoader.add_multi_constructor("", catch_all_constructor)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def safe_path(base_dir: str, path: str) -> str:
    """Resolve absolute path and verify it is strictly within base_dir to prevent path traversal."""
    abs_base = os.path.realpath(base_dir)
    abs_target = os.path.realpath(os.path.join(abs_base, path))

    if os.path.commonpath([abs_base, abs_target]) != abs_base:
        raise PermissionError(f"Access denied: path traversal detected for path '{path}'")
    return abs_target


def _resolve_device(device: str) -> str:
    """Resolve a device name to its YAML filename (without path)."""
    if not device.endswith(".yaml"):
        device = f"{device}.yaml"
    return device


def _device_yaml_path(device: str) -> str:
    """Return the full path to a device YAML file (supporting active & archive dirs)."""
    filename = _resolve_device(device)
    
    # Try active directory first
    try:
        path = safe_path(ESPHOME_DIR, filename)
        if os.path.isfile(path):
            return path
    except PermissionError:
        pass

    # Try archive directory
    try:
        archive_path = safe_path(ESPHOME_DIR, os.path.join("archive", filename))
        if os.path.isfile(archive_path):
            return archive_path
    except PermissionError:
        pass

    # Fallback to the resolved active path (which will be validated later)
    return safe_path(ESPHOME_DIR, filename)


async def _run_async(cmd: list[str], timeout: int = 120, cwd: str | None = None, capture_on_timeout: bool = False) -> str:
    """Run a command asynchronously and return combined stdout+stderr."""
    log.info("Running async command: %s", " ".join(cmd))
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,  # Merges stderr into stdout chronologically
            cwd=cwd or ESPHOME_DIR,
        )
        
        output_lines = []
        
        async def read_stream():
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                output_lines.append(line.decode("utf-8", errors="replace"))
                
        try:
            await asyncio.wait_for(read_stream(), timeout=timeout)
            await proc.wait()
            output = "".join(output_lines).strip()
            if proc.returncode != 0:
                return f"Command failed (exit {proc.returncode}):\n{output}"
            return output
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except OSError:
                pass
            
            output = "".join(output_lines).strip()
            if capture_on_timeout:
                return output
            return f"Command timed out after {timeout}s:\n{output}"
            
    except Exception as e:
        return f"Command failed to start: {e}"


def _parse_device_info(yaml_path: str) -> dict:
    """Parse basic device info from a YAML file, handling custom tags gracefully."""
    try:
        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.load(f, Loader=SecretLoader)

        esphome_section = data.get("esphome", {}) if isinstance(data, dict) else {}
        return {
            "name": esphome_section.get("name", "unknown"),
            "friendly_name": esphome_section.get("friendly_name", ""),
            "file": os.path.basename(yaml_path),
        }
    except Exception as e:
        return {
            "name": "error",
            "friendly_name": "",
            "file": os.path.basename(yaml_path),
            "error": str(e),
        }


def _is_forbidden(filename: str) -> bool:
    """Check if a filename is forbidden for transfer."""
    return os.path.basename(filename).lower() in FORBIDDEN_FILES


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------
def list_devices() -> str:
    """List all available ESPHome device configurations."""
    devices = []

    for path in sorted(glob.glob(os.path.join(ESPHOME_DIR, "*.yaml"))):
        if _is_forbidden(path):
            continue
        try:
            safe_path(ESPHOME_DIR, os.path.basename(path))
            info = _parse_device_info(path)
            info["status"] = "active"
            devices.append(info)
        except PermissionError:
            continue

    archive_dir = os.path.join(ESPHOME_DIR, "archive")
    if os.path.isdir(archive_dir):
        for path in sorted(glob.glob(os.path.join(archive_dir, "*.yaml"))):
            try:
                safe_path(ESPHOME_DIR, os.path.join("archive", os.path.basename(path)))
                info = _parse_device_info(path)
                info["status"] = "archived"
                devices.append(info)
            except PermissionError:
                continue

    if not devices:
        return "No device configurations found."

    lines = ["ESPHome Devices:", ""]
    for d in devices:
        name = d["name"]
        friendly = f' ("{d["friendly_name"]}")' if d.get("friendly_name") else ""
        status = f" [{d['status']}]" if d["status"] == "archived" else ""
        error = f" ERROR: {d['error']}" if d.get("error") else ""
        lines.append(f"  - {name}{friendly}{status} ({d['file']}){error}")

    return "\n".join(lines)


async def validate(device: str, timeout: int | None = None) -> str:
    """Validate an ESPHome device config."""
    try:
        yaml_path = _device_yaml_path(device)
        if not os.path.isfile(yaml_path):
            return f"Device config not found: {yaml_path}"
        actual_timeout = timeout if timeout is not None else VALIDATE_TIMEOUT
        return await _run_async([ESPHOME_BIN, "config", yaml_path], timeout=actual_timeout)
    except PermissionError as e:
        return str(e)


async def compile_device(device: str, timeout: int | None = None) -> str:
    """Compile ESPHome firmware for a device."""
    try:
        yaml_path = _device_yaml_path(device)
        if not os.path.isfile(yaml_path):
            return f"Device config not found: {yaml_path}"
        actual_timeout = timeout if timeout is not None else COMPILE_TIMEOUT
        return await _run_async([ESPHOME_BIN, "compile", yaml_path], timeout=actual_timeout)
    except PermissionError as e:
        return str(e)


async def flash(device: str, port: str = "OTA", timeout: int | None = None) -> str:
    """OTA/serial flash a device."""
    try:
        yaml_path = _device_yaml_path(device)
        if not os.path.isfile(yaml_path):
            return f"Device config not found: {yaml_path}"
        actual_timeout = timeout if timeout is not None else FLASH_TIMEOUT
        return await _run_async([ESPHOME_BIN, "run", yaml_path, "--no-logs", "--device", port], timeout=actual_timeout)
    except PermissionError as e:
        return str(e)


async def logs(device: str, num_lines: int = 50, duration: int = 5, port: str = "OTA") -> str:
    """Get recent logs from an ESPHome device."""
    try:
        yaml_path = _device_yaml_path(device)
        if not os.path.isfile(yaml_path):
            return f"Device config not found: {yaml_path}"
        # We enforce a timeout on the ESPHome logs CLI itself via asyncio timeout
        actual_duration = max(1, duration)
        output = await _run_async([ESPHOME_BIN, "logs", yaml_path, "--device", port], timeout=actual_duration, capture_on_timeout=True)
        lines = output.splitlines()
        if len(lines) > num_lines:
            lines = lines[-num_lines:]
        return "\n".join(lines)
    except PermissionError as e:
        return str(e)


def push_files(files: dict[str, str]) -> str:
    """Write YAML files to the ESPHome config directory safely."""
    if not isinstance(files, dict):
        return (
            f"Error: The 'files' argument must be a dictionary (JSON object) mapping "
            f"filenames to their YAML contents. Example:\n"
            f'{{"device.yaml": "esphome:\\n  name: statusdisplay\\n..."}}\n'
            f"Got: {type(files).__name__} ({files!r}). Please retry with a dictionary."
        )
    results = []
    for filename, content in files.items():
        if _is_forbidden(filename):
            results.append(f"{filename}: REJECTED (secrets files cannot be pushed)")
            continue
        if not filename.endswith(".yaml"):
            results.append(f"{filename}: REJECTED (only .yaml files allowed)")
            continue

        try:
            # Enforce path traversal check
            target = safe_path(ESPHOME_DIR, filename)
            os.makedirs(os.path.dirname(target), exist_ok=True)

            with open(target, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            results.append(f"{filename}: OK")
        except PermissionError as e:
            results.append(f"{filename}: REJECTED ({e})")
        except OSError as e:
            results.append(f"{filename}: ERROR ({e})")

    return "Push results:\n" + "\n".join(results)


def pull_files(filenames: list[str] | None = None) -> dict[str, str]:
    """Read YAML files from the ESPHome config directory safely."""
    result = {}

    if filenames is None:
        # Pull all YAML files in the base and archive directory
        paths = sorted(glob.glob(os.path.join(ESPHOME_DIR, "*.yaml")))
        archive_dir = os.path.join(ESPHOME_DIR, "archive")
        if os.path.isdir(archive_dir):
            paths += sorted(glob.glob(os.path.join(archive_dir, "*.yaml")))
    else:
        paths = []
        for fn in filenames:
            if not fn.endswith(".yaml"):
                fn = f"{fn}.yaml"
            
            # Resolve and add paths while preventing escape
            try:
                path = safe_path(ESPHOME_DIR, fn)
                if os.path.isfile(path):
                    paths.append(path)
                else:
                    archive_path = safe_path(ESPHOME_DIR, os.path.join("archive", fn))
                    if os.path.isfile(archive_path):
                        paths.append(archive_path)
            except PermissionError:
                continue

    for path in paths:
        if _is_forbidden(path):
            continue
        try:
            # Re-verify path safety before reading
            rel = os.path.relpath(path, ESPHOME_DIR)
            safe_path(ESPHOME_DIR, rel)
            with open(path, encoding="utf-8") as f:
                result[rel] = f.read()
        except PermissionError as e:
            result[os.path.basename(path)] = f"ERROR: {e}"
        except OSError as e:
            result[os.path.basename(path)] = f"ERROR: {e}"

    return result


def push_fonts(files: dict[str, str]) -> str:
    """Write font files to the ESPHome fonts directory safely."""
    if not isinstance(files, dict):
        return (
            f"Error: The 'files' argument must be a dictionary (JSON object) mapping "
            f"font filenames to their base64-encoded file contents. Example:\n"
            f'{{"font.ttf": "YmFzZTY0IGNvbnRlbnQ="}}\n'
            f"Got: {type(files).__name__} ({files!r}). Please retry with a dictionary."
        )
    fonts_dir = os.path.join(ESPHOME_DIR, "fonts")
    os.makedirs(fonts_dir, exist_ok=True)

    results = []
    for filename, b64_content in files.items():
        try:
            # Enforce path safety relative to fonts_dir
            target = safe_path(fonts_dir, os.path.basename(filename))
            data = base64.b64decode(b64_content)
            with open(target, "wb") as f:
                f.write(data)
            results.append(f"{filename}: OK ({len(data)} bytes)")
        except PermissionError as e:
            results.append(f"{filename}: REJECTED ({e})")
        except Exception as e:
            results.append(f"{filename}: ERROR ({e})")

    return "Font push results:\n" + "\n".join(results)


def pull_fonts(filenames: list[str] | None = None) -> dict[str, str]:
    """Read font files from the ESPHome fonts directory safely."""
    fonts_dir = os.path.join(ESPHOME_DIR, "fonts")
    result = {}

    if not os.path.isdir(fonts_dir):
        return result

    if filenames is None:
        paths = sorted(glob.glob(os.path.join(fonts_dir, "*")))
    else:
        paths = []
        for fn in filenames:
            try:
                path = safe_path(fonts_dir, os.path.basename(fn))
                if os.path.isfile(path):
                    paths.append(path)
            except PermissionError:
                continue

    for path in paths:
        if not os.path.isfile(path):
            continue
        try:
            rel = os.path.relpath(path, fonts_dir)
            safe_path(fonts_dir, rel)
            with open(path, "rb") as f:
                data = f.read()
            result[os.path.basename(path)] = base64.b64encode(data).decode("ascii")
        except PermissionError as e:
            result[os.path.basename(path)] = f"ERROR: {e}"
        except OSError as e:
            result[os.path.basename(path)] = f"ERROR: {e}"

    return result
