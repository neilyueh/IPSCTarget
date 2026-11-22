#!/bin/bash
# Double-click once to make this Mac start the IPSC 靶監看 web server at every login.
# After that, open http://localhost:8765/index.html in Chrome any time.
# The server (serve.py) is also reachable from an iPad on the same Wi-Fi. Safe to run again,
# e.g. after moving the project folder.

LABEL="com.ipsctarget.monitor-web"
PORT=8765
DIR="$(cd "$(dirname "$0")" && pwd)" || exit 1
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PY="$(command -v python3)"

if [ -z "$PY" ]; then
  echo "找不到 python3。請先在終端機執行 xcode-select --install（或用 Homebrew 安裝 python）後再試一次。"
  exit 1
fi

# Stop an earlier copy of this server, and the one start.command may have started.
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
pkill -f "http.server $PORT" 2>/dev/null
pkill -f "serve.py $PORT" 2>/dev/null
sleep 1

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string>
    <string>$DIR/serve.py</string>
    <string>$PORT</string>
  </array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/ipsctarget-web.log</string>
</dict>
</plist>
PLISTEOF

launchctl bootstrap "gui/$(id -u)" "$PLIST" || { echo "啟動失敗"; exit 1; }

URL="http://localhost:$PORT/index.html"
for _ in 1 2 3 4 5 6 7 8 9 10; do
  curl -s -o /dev/null "$URL" && { echo "完成！以後登入就會自動啟動。網址：$URL"; exit 0; }
  sleep 0.5
done
echo "伺服器沒有回應，請看 ~/Library/Logs/ipsctarget-web.log"
exit 1
