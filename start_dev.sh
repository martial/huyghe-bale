#!/usr/bin/env bash
# Opens iTerm2 with two tabs:
#   Tab 1 — Flask backend
#   Tab 2 — Vite frontend dev server (:5173), proxying /api to backend

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Find a free port (try 5001, fallback to random)
PORT=$(python3 -c "
import socket
s = socket.socket()
try:
    s.bind(('0.0.0.0', 5001)); port = 5001
except OSError:
    s.bind(('0.0.0.0', 0)); port = s.getsockname()[1]
s.close()
print(port)
")

echo "Backend port: $PORT"

osascript <<EOF
tell application "iTerm"
  activate

  -- New window with Flask tab
  set newWindow to (create window with default profile)
  tell current session of newWindow
    write text "cd \"$SCRIPT_DIR/admin/backend\" && FLASK_PORT=$PORT .venv/bin/python app.py"
  end tell

  -- New tab for Vite
  tell newWindow
    set viteTab to (create tab with default profile)
    tell current session of viteTab
      write text "cd \"$SCRIPT_DIR/admin/frontend\" && VITE_BACKEND_PORT=$PORT npm run dev"
    end tell
  end tell

end tell
EOF

echo "Dev servers launching in iTerm2"
echo "  Tab 1 → Flask backend  :$PORT"
echo "  Tab 2 → Vite frontend  :5173 → proxy /api → :$PORT"
