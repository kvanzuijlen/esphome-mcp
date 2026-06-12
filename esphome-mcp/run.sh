#!/usr/bin/with-contenv bashio
# ==============================================================================
# ESPHome MCP Server — Add-on entry point
# ==============================================================================
set -e

# Read auth token from add-on config
AUTH_TOKEN="$(bashio::config 'auth_token')"

# Run network diagnostics on startup
bashio::log.info "Running network diagnostics..."
if curl -s -I --connect-timeout 5 https://pypi.org/ >/dev/null; then
    bashio::log.info "Network check: Connected to PyPI successfully."
else
    bashio::log.error "Network check: Failed to connect to PyPI!"
    if ping -c 1 -W 2 1.1.1.1 >/dev/null; then
        bashio::log.error "Network check: Direct IP ping (1.1.1.1) succeeded. This indicates a DNS resolution issue inside the container."
    else
        bashio::log.error "Network check: Direct IP ping (1.1.1.1) failed. The container has no network access."
    fi
fi


# Auto-generate token if not configured
if [ -z "$AUTH_TOKEN" ] || [ "$AUTH_TOKEN" = "null" ]; then
    TOKEN_FILE="/data/auth_token"
    if [ ! -f "$TOKEN_FILE" ]; then
        AUTH_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
        echo "$AUTH_TOKEN" > "$TOKEN_FILE"
        bashio::log.info "Generated new auth token — retrieve it from the add-on logs"
    else
        AUTH_TOKEN="$(cat "$TOKEN_FILE")"
    fi
    bashio::log.warning "==================================================="
    bashio::log.warning "  MCP Auth Token: ${AUTH_TOKEN}"
    bashio::log.warning "==================================================="
    bashio::log.warning "Set ESPHOME_MCP_TOKEN in your Claude Code environment"
    bashio::log.warning "to this value, or configure it in the add-on options."
fi

export ESPHOME_MCP_AUTH_TOKEN="$AUTH_TOKEN"
export ESPHOME_DIR="/config/esphome"

# Load and export timeouts from add-on config if set
if bashio::config.has_value 'compile_timeout'; then
    export ESPHOME_COMPILE_TIMEOUT="$(bashio::config 'compile_timeout')"
    bashio::log.info "Compile timeout set to: ${ESPHOME_COMPILE_TIMEOUT}s"
fi
if bashio::config.has_value 'flash_timeout'; then
    export ESPHOME_FLASH_TIMEOUT="$(bashio::config 'flash_timeout')"
    bashio::log.info "Flash timeout set to: ${ESPHOME_FLASH_TIMEOUT}s"
fi
if bashio::config.has_value 'validate_timeout'; then
    export ESPHOME_VALIDATE_TIMEOUT="$(bashio::config 'validate_timeout')"
    bashio::log.info "Validate timeout set to: ${ESPHOME_VALIDATE_TIMEOUT}s"
fi

# Set PlatformIO Core dir to persistent /data partition to cache toolchains
export PLATFORMIO_CORE_DIR="/data/.platformio"
bashio::log.info "PlatformIO cache configured at: ${PLATFORMIO_CORE_DIR}"

# Force one-time cleanup of PlatformIO env for glibc & python-dev updates
CLEANUP_MARKER="/data/.mcp_env_cleaned_v1"
if [ ! -f "$CLEANUP_MARKER" ]; then
    bashio::log.warning "Performing one-time environment cleanup for PlatformIO compiler updates..."
    rm -rf "${PLATFORMIO_CORE_DIR}/penv"
    rm -rf "${PLATFORMIO_CORE_DIR}/.cache"
    touch "$CLEANUP_MARKER"
fi

# Clean up broken/incompatible PlatformIO virtualenvs (e.g. after Python updates)
if [ -d "${PLATFORMIO_CORE_DIR}/penv" ]; then
    if ! "${PLATFORMIO_CORE_DIR}/penv/bin/python" --version >/dev/null 2>&1; then
        bashio::log.warning "PlatformIO virtualenv is broken or incompatible. Recreating..."
        rm -rf "${PLATFORMIO_CORE_DIR}/penv"
    fi
fi

bashio::log.info "Starting ESPHome MCP Server on port 8099..."
exec python3 -m server.main
