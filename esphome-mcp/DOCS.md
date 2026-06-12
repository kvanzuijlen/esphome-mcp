# ESPHome MCP Server for Home Assistant

This add-on exposes ESPHome command-line operations (compile, validate, OTA flash, serial flash, logs, and config file synchronization) as secure Model Context Protocol (MCP) tools. You can use it to let AI agents like Claude Code inspect, build, and deploy your ESPHome configuration files.

---

## Getting Started

### 1. Configure the Add-on
Go to the **Configuration** tab to customize the default timeouts and authentication:

- **`auth_token`**: Keep this blank to automatically generate a secure 32-character token on every start, or set a permanent, custom static token.
- **`compile_timeout`**: The default maximum compile duration in seconds (defaults to `300`).
- **`flash_timeout`**: The default maximum flash duration in seconds (defaults to `600`).
- **`validate_timeout`**: The default maximum configuration validation duration in seconds (defaults to `120`).

### 2. Start the Add-on
Click **Start** on the Info page.

### 3. Retrieve your Auth Token
If you left `auth_token` blank, open the **Log** tab of the add-on. You will see a block like this:

```text
===================================================
  MCP Auth Token: YOUR_AUTO_GENERATED_SECURE_TOKEN
===================================================
```
Copy this token. You will need it to authenticate your AI client.

---

## Connecting Your AI Client

The add-on runs a stateless, streamable HTTP MCP server on port **`8099`**. The MCP endpoint path is **`/mcp`**.

### For Claude Code
To configure Claude Code, edit your `claude_desktop_config.json` file:

```json
{
  "mcpServers": {
    "esphome": {
      "command": "curl",
      "args": [
        "-s",
        "-N",
        "-H", "Authorization: Bearer YOUR_AUTH_TOKEN",
        "http://<YOUR_HOME_ASSISTANT_IP>:8099/mcp"
      ]
    }
  }
}
```

Replace `<YOUR_HOME_ASSISTANT_IP>` with the IP address of your Home Assistant server, and `YOUR_AUTH_TOKEN` with the token copied from the logs.

---

## How It Works Under the Hood

- **Path Security**: The add-on strictly validates paths, allowing file operations only within the `/config/esphome/` directory. Secrets (like `secrets.yaml`) are blocked from being pulled or pushed for security.
- **Compilation Caching**: PlatformIO core downloads compilers, SDKs, and libraries inside `/data/.platformio` (a persistent partition). The first compilation of a device might take a few minutes as it downloads components, but subsequent compiles will be cached and fast.
- **Alpine/Musl Compatibility**: The add-on includes native compatibility packages (`gcompat`, `libc6-compat`, `python3-dev`, `build-base`) so that PlatformIO's precompiled compilers and package managers run flawlessly.
- **Log Streaming**: When you run `esphome_logs`, the add-on captures the logs for the specified duration and closes the stream properly so that the AI client doesn't hang.

---

## Troubleshooting

### Dynamic Timeouts
If a compilation or flashing process times out, you don't necessarily have to restart or change the add-on options. The AI agent can override the timeout dynamically by passing a higher `timeout` argument (e.g. `esphome_compile(device="...", timeout=600)`).

### Network Issues inside the Add-on
On startup, the add-on performs network diagnostic tests to confirm it can contact PyPI. If it fails:
- Check the add-on logs. If it reports a DNS error, check your Home Assistant network configuration.
- Check if your Home Assistant instance has internet access.

### Rebuilding the Add-on
If you update the add-on and notice platform errors, click **Rebuild** on the add-on details page to ensure all native compiler packages are freshly baked into the image.
