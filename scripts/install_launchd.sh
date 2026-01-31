#!/bin/bash
# Install Job Radar as a launchd service

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PLIST_FILE="$PROJECT_DIR/launchd/com.sammontoya.jobradar.plist"
LAUNCHD_DIR="$HOME/Library/LaunchAgents"
LOGS_DIR="$PROJECT_DIR/logs"

echo "Job Radar launchd Installation"
echo "=============================="
echo

# Create logs directory
mkdir -p "$LOGS_DIR"
echo "Created logs directory: $LOGS_DIR"

# Create LaunchAgents directory if needed
mkdir -p "$LAUNCHD_DIR"

# Copy plist to LaunchAgents
DEST_PLIST="$LAUNCHD_DIR/com.sammontoya.jobradar.plist"

# Unload if already loaded
if launchctl list | grep -q "com.sammontoya.jobradar"; then
    echo "Unloading existing service..."
    launchctl unload "$DEST_PLIST" 2>/dev/null || true
fi

# Copy plist
cp "$PLIST_FILE" "$DEST_PLIST"
echo "Copied plist to: $DEST_PLIST"

# Load the service
launchctl load "$DEST_PLIST"
echo "Service loaded"

# Check status
echo
echo "Service status:"
launchctl list | grep "com.sammontoya.jobradar" || echo "Service not running yet"

echo
echo "Installation complete!"
echo
echo "Commands:"
echo "  Start:   launchctl start com.sammontoya.jobradar"
echo "  Stop:    launchctl stop com.sammontoya.jobradar"
echo "  Restart: launchctl kickstart -k gui/\$(id -u)/com.sammontoya.jobradar"
echo "  Logs:    tail -f $LOGS_DIR/jobradar.log"
echo "  Errors:  tail -f $LOGS_DIR/jobradar.error.log"
echo
echo "To uninstall:"
echo "  launchctl unload $DEST_PLIST"
echo "  rm $DEST_PLIST"
