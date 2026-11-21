#!/bin/bash
# Double-click to stop the IPSC 靶監看 web server from starting at login.
LABEL="com.ipsctarget.monitor-web"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "已移除開機自動啟動。"
