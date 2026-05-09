#!/bin/bash
cd "$(dirname "$0")"
APP_PATH="apps/desktop/src-tauri/target/release/bundle/macos/MemeTraderPro.app"
if [ -d "$APP_PATH" ]; then
  /usr/bin/open -n "$APP_PATH"
  exit 0
fi

PYTHON_BIN="trading_env/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi

if /usr/bin/curl -fsS --max-time 1 "http://127.0.0.1:8765/api/health" >/dev/null 2>&1; then
  /usr/bin/open "http://127.0.0.1:8765/"
  exit 0
fi

API_TOKEN="$(/usr/bin/uuidgen | /usr/bin/tr '[:upper:]' '[:lower:]')"
MTP_DESKTOP_API_TOKEN="$API_TOKEN" "$PYTHON_BIN" desktop_api.py --host 127.0.0.1 --port 8765 &
sleep 1
/usr/bin/open "http://127.0.0.1:8765/"
