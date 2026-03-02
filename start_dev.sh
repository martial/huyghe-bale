#!/usr/bin/env bash
# Opens iTerm2 with two tabs:
#   Tab 1 — Flask backend (:5001)
#   Tab 2 — Vite frontend dev server (:5173)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

osascript <<EOF
tell application "iTerm"
  activate

  -- New window with Flask tab
  set newWindow to (create window with default profile)
  tell current session of newWindow
    write text "cd \"$SCRIPT_DIR/admin/backend\" && .venv/bin/python -m flask --app app run --port 5001 --debug"
  end tell

  -- New tab for Vite
  tell newWindow
    set viteTab to (create tab with default profile)
    tell current session of viteTab
      write text "cd \"$SCRIPT_DIR/admin/frontend\" && npm run dev"
    end tell
  end tell

end tell
EOF

echo "Dev servers launching in iTerm2"
echo "  Tab 1 → Flask backend  :5001"
echo "  Tab 2 → Vite frontend  :5173"
