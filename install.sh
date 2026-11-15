#!/bin/bash
# Schedules tracker.py to run every day at the given time (default 09:00) on this Mac.
# Usage: ./install.sh [HOUR] [MINUTE]     e.g. ./install.sh 8 30
#        ./install.sh uninstall
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
LABEL="com.collectr.tracker"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ "$1" = "uninstall" ]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"; echo "Removed the daily schedule."; exit 0
fi

HOUR="${1:-9}"; MINUTE="${2:-0}"
PY="$(command -v python3)"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>
    <string>$PY</string><string>$DIR/tracker.py</string><string>run</string>
  </array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>StartCalendarInterval</key><dict>
    <key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>$MINUTE</integer>
  </dict>
  <key>StandardOutPath</key><string>$DIR/tracker.log</string>
  <key>StandardErrorPath</key><string>$DIR/tracker.log</string>
</dict></plist>
EOF
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
printf "Scheduled: every day at %02d:%02d (weekly report on Sundays).\nLog: %s/tracker.log\n" "$HOUR" "$MINUTE" "$DIR"
