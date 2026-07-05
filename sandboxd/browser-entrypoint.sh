#!/bin/bash
# browser-entrypoint.sh — Browser sandbox entrypoint
#
# VNC chain (CORRECT):
#   1. Xvfb    — virtual framebuffer on display :99
#   2. Chromium — headless browser with remote debugging on :9222
#   3. x11vnc  — VNC server on :5900, bound to display :99
#   4. websockify — serves noVNC client on :6080, proxies WebSocket → VNC :5900
#
# ⚠ The DeepSeek draft's `websockify 6080 localhost:9222` was WRONG.
#    noVNC speaks VNC protocol, NOT Chrome DevTools Protocol.
#    The correct proxy target is the VNC server (localhost:5900), not CDP (9222).

set -e

# 1. Start Xvfb on display :99 (1280x720x24)
echo "[browser-entrypoint] Starting Xvfb on :99..."
Xvfb :99 -screen 0 1280x720x24 -ac +extension GLX +render -noreset &
XVFB_PID=$!

# Wait for Xvfb to be ready
sleep 1

export DISPLAY=:99

# 2. Launch Chromium with remote debugging (NOT headless — we want a visible window in VNC)
echo "[browser-entrypoint] Starting Chromium with CDP on :9222..."
chromium \
    --no-sandbox \
    --disable-gpu \
    --disable-dev-shm-usage \
    --disable-software-rasterizer \
    --remote-debugging-port=9222 \
    --remote-debugging-address=0.0.0.0 \
    --window-size=1280,720 \
    --no-first-run \
    --disable-default-apps \
    --disable-extensions \
    --disable-background-networking \
    --no-default-browser-check \
    "about:blank" &
CHROMIUM_PID=$!

# Wait for Chromium CDP to be ready
echo "[browser-entrypoint] Waiting for CDP on :9222..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:9222/json/version > /dev/null 2>&1; then
        echo "[browser-entrypoint] CDP ready."
        break
    fi
    sleep 1
done

# 3. Start x11vnc bound to display :99 on port 5900
echo "[browser-entrypoint] Starting x11vnc on :5900..."
x11vnc -display :99 -forever -shared -rfbport 5900 -nopw -bg -o /tmp/x11vnc.log

# 4. Start websockify: serves noVNC client on :6080, proxies WebSocket → VNC :5900
#    --web /usr/share/novnc serves the noVNC HTML/JS client
#    6080 is the listen port
#    localhost:5900 is the VNC server (NOT 9222/CDP!)
echo "[browser-entrypoint] Starting websockify + noVNC on :6080..."
websockify --web /usr/share/novnc 6080 localhost:5900 &
WEBSOCKIFY_PID=$!

echo "[browser-entrypoint] Browser sandbox ready."
echo "  noVNC:  http://localhost:6080/vnc.html"
echo "  CDP:    http://localhost:9222"

# Trap signals for clean shutdown
cleanup() {
    echo "[browser-entrypoint] Shutting down..."
    kill $WEBSOCKIFY_PID $CHROMIUM_PID $XVFB_PID 2>/dev/null || true
    wait $WEBSOCKIFY_PID $CHROMIUM_PID $XVFB_PID 2>/dev/null || true
}
trap cleanup SIGTERM SIGINT

# Wait for any child to exit (keeps container alive)
wait -n $XVFB_PID $CHROMIUM_PID $WEBSOCKIFY_PID
cleanup
