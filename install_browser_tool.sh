#!/bin/bash
# install_browser_tool.sh
# Installs browser_interact_tool.py into the nik29-coordinator container
# and registers it in the custom_tools_loader.

set -e

CONTAINER_NAME="nik29-coordinator"
TOOL_FILE="$(dirname "$(realpath "$0")")/browser_interact_tool.py"
CONTAINER_TOOLS_DIR="/app/app/tools"
CONTAINER_TOOL_PATH="${CONTAINER_TOOLS_DIR}/browser_interact_tool.py"

# Possible locations for custom_tools_loader
LOADER_CANDIDATES=(
    "/app/app/tools/custom_tools_loader.py"
    "/app/app/custom_tools_loader.py"
    "/app/custom_tools_loader.py"
)

echo "=============================="
echo "  nik29 Browser Tool Installer"
echo "=============================="
echo ""

# 1. Check that the tool file exists locally
if [ ! -f "$TOOL_FILE" ]; then
    echo "[ERROR] Tool file not found: $TOOL_FILE"
    exit 1
fi
echo "[OK] Tool file found: $TOOL_FILE"

# 2. Check that the container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "[ERROR] Container '${CONTAINER_NAME}' is not running."
    echo "        Start it first with: docker start ${CONTAINER_NAME}"
    exit 1
fi
echo "[OK] Container '${CONTAINER_NAME}' is running"

# 3. Ensure the tools directory exists in the container
docker exec "$CONTAINER_NAME" mkdir -p "$CONTAINER_TOOLS_DIR"
echo "[OK] Tools directory ensured: ${CONTAINER_TOOLS_DIR}"

# 4. Copy the tool file into the container
docker cp "$TOOL_FILE" "${CONTAINER_NAME}:${CONTAINER_TOOL_PATH}"
echo "[OK] Tool file copied to container: ${CONTAINER_TOOL_PATH}"

# 5. Ensure playwright is installed in the container
echo "[...] Checking Playwright installation inside container..."
if docker exec "$CONTAINER_NAME" python3 -c "from playwright.async_api import async_playwright" 2>/dev/null; then
    echo "[OK] Playwright already installed"
else
    echo "[...] Installing Playwright inside container..."
    docker exec "$CONTAINER_NAME" pip install playwright 2>&1 | tail -5
    docker exec "$CONTAINER_NAME" python3 -m playwright install chromium 2>&1 | tail -5
    echo "[OK] Playwright installed"
fi

# 6. Find and update custom_tools_loader
LOADER_PATH=""
for candidate in "${LOADER_CANDIDATES[@]}"; do
    if docker exec "$CONTAINER_NAME" test -f "$candidate" 2>/dev/null; then
        LOADER_PATH="$candidate"
        break
    fi
done

IMPORT_LINE="from app.tools.browser_interact_tool import browser_interact, TOOL_DEFINITION as browser_interact_TOOL_DEFINITION"

if [ -n "$LOADER_PATH" ]; then
    echo "[OK] Found custom_tools_loader at: ${LOADER_PATH}"
    
    # Check if import is already present
    if docker exec "$CONTAINER_NAME" grep -q "browser_interact_tool" "$LOADER_PATH" 2>/dev/null; then
        echo "[OK] Import already present in custom_tools_loader — skipping"
    else
        # Append import line to the loader
        docker exec "$CONTAINER_NAME" bash -c "echo '' >> '${LOADER_PATH}' && echo '${IMPORT_LINE}' >> '${LOADER_PATH}'"
        echo "[OK] Import line appended to custom_tools_loader"
    fi
else
    echo "[WARN] custom_tools_loader not found in expected locations."
    echo "       Please add the following import manually:"
    echo "       ${IMPORT_LINE}"
fi

# 7. Restart the container
echo ""
echo "[...] Restarting container '${CONTAINER_NAME}'..."
docker restart "$CONTAINER_NAME"
echo "[OK] Container restarted"

# 8. Wait for container to be ready
echo "[...] Waiting for container to be ready..."
sleep 5

# 9. Quick sanity check
echo "[...] Running sanity check..."
if docker exec "$CONTAINER_NAME" python3 -c "
import sys
sys.path.insert(0, '/app')
from app.tools.browser_interact_tool import TOOL_DEFINITION
print('Tool name:', TOOL_DEFINITION['name'])
print('Actions:', TOOL_DEFINITION['parameters']['properties']['action']['enum'])
" 2>&1; then
    echo ""
    echo "[SUCCESS] browser_interact_tool is installed and importable!"
else
    echo ""
    echo "[WARN] Sanity check failed. Check container logs:"
    echo "       docker logs ${CONTAINER_NAME} --tail 50"
fi

echo ""
echo "=============================="
echo "  Installation complete"
echo "=============================="
