#!/bin/bash
# Double-click to open IPSC 靶監看 at http://localhost:8765/ instead of as a file.
# Chrome remembers microphone and Bluetooth permission for a localhost address,
# but not for a page opened straight from a file, so this stops the
# "use microphone?" prompt from coming back every time.
# The little web server (serve.py) is also reachable from an iPad on the same Wi-Fi;
# the page header shows the address to use there.

cd "$(dirname "$0")" || exit 1
PORT=8765
URL="http://localhost:$PORT/index.html"

if ! lsof -nP -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1; then
  nohup python3 serve.py "$PORT" >/dev/null 2>&1 &
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    curl -s -o /dev/null "$URL" && break
    sleep 0.3
  done
fi

if [ -d "/Applications/Google Chrome.app" ]; then
  open -a "Google Chrome" "$URL"
else
  open "$URL"
fi
