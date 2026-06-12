# ESPHome MCP Server for Home Assistant

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Home Assistant Add-on](https://img.shields.io/badge/Home%20Assistant-Add--on-blue.svg)](https://www.home-assistant.io/)

[![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fkvanzuijlen%2Fesphome-mcp)

A security-hardened, high-performance **Model Context Protocol (MCP)** server built as a Home Assistant Add-on. It exposes the ESPHome command-line toolset as secure, isolated tools for AI coding assistants like Claude Code, allowing your AI agent to list, validate, compile, flash, and view logs for your ESPHome devices directly.

---

## ⚡ Features

- **Full ESPHome Toolset**: Exposes compile, validate, OTA/serial flash, and log-streaming commands as MCP tools.
- **Bi-directional File Sync**: Copy configurations (`.yaml` files) and assets (`fonts/`) back and forth between the Home Assistant ESPHome config directory and your local AI workspace.
- **Smart Log Streaming**: Captures ESPHome logs asynchronously over a specified duration with automatic partial buffers on timeout.
- **Dynamic Timeouts**: Global add-on timeout defaults with dynamic override parameters for each compilation, validation, or flashing command, letting the AI adjust them when compiling complex boards.
- **PlatformIO Cache Persistence**: Caches compilation libraries and tools in Home Assistant's persistent `/data` partition, ensuring compilation speedups after the first run.
- **Auto-healing Virtual Environment**: Automatically detects and heals broken or incompatible PlatformIO environments (e.g. after container updates) without manual intervention.
- **Bearer Authentication**: Secure bearer token validation on all endpoints. If no token is provided, a secure random token is automatically generated and displayed in the Add-on logs on startup.

---

## 🏗️ Architecture

The ESPHome MCP Server runs as a Home Assistant Add-on and exposes a **Streamable HTTP MCP** server using `FastMCP`. 

```
[Claude Code / AI Client] <==> (MCP over HTTP / Bearer Auth) <==> [FastMCP Server :8099/mcp]
                                                                        ||
                                                        (Subprocess / Local Filesystem)
                                                                        ||
                                                                        \/
                                                        [ESPHome CLI & Config Files]
```

- **Host Environment**: Alpine-based Home Assistant Add-on container.
- **Alpine / Musl Support**: Pre-baked with `gcompat`, `libc6-compat`, `python3-dev`, and `build-base` to prevent compilation failures of Python wheels or compiler `glibc` linking errors (like CMake or PlatformIO compiler toolchain).
- **Transport**: FastMCP native `streamable_http_app` listening on port `8099/mcp`.

---

## 📦 Installation & Setup

### 1. Add Custom Repository to Home Assistant
1. In Home Assistant, navigate to **Settings** -> **Add-ons** -> **Add-on Store**.
2. Click the three dots (top-right corner) and select **Repositories**.
3. Add the URL of your repository: `https://github.com/kvanzuijlen/esphome-mcp`
4. Click **Add**, then close the dialog.

### 2. Install the Add-on
1. Find **ESPHome MCP Server (Custom)** in the Add-on store list and click **Install**.
2. Wait for the installation to finish.

### 3. Configuration
Navigate to the **Configuration** tab of the Add-on to set up optional parameters:

| Option | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `auth_token` | `str?` | *(Auto-generated)* | Static Bearer token for client authentication. Leave blank for auto-generation. |
| `compile_timeout` | `int?` | `300` | Global default timeout (seconds) for compilation. |
| `flash_timeout` | `int?` | `600` | Global default timeout (seconds) for OTA/serial flashing. |
| `validate_timeout` | `int?` | `120` | Global default timeout (seconds) for config validation. |

Click **Save**, then start the Add-on.

### 4. Fetch the Authentication Token
If you did not configure a static `auth_token`, view the **Log** tab of the Add-on. You will see a banner containing your auto-generated secure token:

```text
===================================================
  MCP Auth Token: YOUR_AUTO_GENERATED_SECURE_TOKEN
===================================================
Set ESPHOME_MCP_TOKEN in your Claude Code environment
to this value, or configure it in the add-on options.
```

---

## 🤖 AI Client Integration

To connect Claude Code (or another MCP host) to the ESPHome MCP Server, add the server to your client configuration.

### For Claude Code (`claude_desktop_config.json`)
Add the following to your configuration file (usually located at `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "esphome": {
      "command": "curl",
      "args": [
        "-s",
        "-N",
        "-H", "Authorization: Bearer YOUR_AUTH_TOKEN",
        "http://homeassistant.local:8099/mcp"
      ]
    }
  }
}
```
*(Replace `homeassistant.local` with your Home Assistant host address if different, and `YOUR_AUTH_TOKEN` with your static or auto-generated token).*

---

## 🛠️ Available MCP Tools

The ESPHome MCP Server exposes the following capabilities:

### Device Management & Configuration
*   `esphome_list_devices()`: Scans the `/config/esphome` directory and lists all configured YAML devices.
*   `esphome_validate(device: str, timeout: int | None)`: Syntactically validates a YAML device configuration file.
*   `esphome_push_files(files: dict)`: Pushes new or modified YAML configurations into `/config/esphome/` (except `secrets.yaml`).
*   `esphome_pull_files(filenames: list | None)`: Retrieves YAML configurations from `/config/esphome/` (except `secrets.yaml`).

### Build & Deploy
*   `esphome_compile(device: str, timeout: int | None)`: Compiles the device firmware binary.
*   `esphome_flash(device: str, port: str, timeout: int | None)`: Compiles and uploads/flashes firmware to a target device (OTA address or serial port).
*   `esphome_logs(device: str, num_lines: int, duration: int, port: str)`: Streams a real-time slice of logs from the device (OTA or serial) for a specific duration (default 5s).

### Assets
*   `esphome_push_fonts(files: dict)`: Pushes base64-encoded font files to the `/config/esphome/fonts/` directory.
*   `esphome_pull_fonts(filenames: list | None)`: Retrieves base64-encoded font files from Home Assistant.

---

## 🧪 Development & Testing

The repository comes equipped with a comprehensive test suite in the `tests/` directory.

### Running Unit Tests Locally
Make sure you have python 3.11+ and the requirements installed.

```bash
# Install dependencies
pip install -r requirements.txt
pip install pytest

# Run tests
pytest tests/
```

The test suite runs 14 synchronous and asynchronous test cases covering path validation, timeout enforcement, log capturing, and authentication middleware.

---

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
