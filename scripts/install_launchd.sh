#!/bin/bash
# Install Job Radar as a launchd service (macOS only)
# Generates a plist from the .example template with auto-detected paths.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVICE_NAME="com.jobradar"
TEMPLATE="$PROJECT_DIR/launchd/com.jobradar.plist.example"
GENERATED="$PROJECT_DIR/launchd/com.jobradar.plist"
LAUNCHD_DIR="$HOME/Library/LaunchAgents"
LOGS_DIR="$PROJECT_DIR/logs"

echo "Job Radar launchd Installation"
echo "=============================="
echo

# Verify template exists
if [ ! -f "$TEMPLATE" ]; then
    echo "ERROR: Template not found at $TEMPLATE"
    exit 1
fi

# Create logs directory
mkdir -p "$LOGS_DIR"
echo "Created logs directory: $LOGS_DIR"

# Generate plist from template by replacing YOUR_PROJECT_PATH
sed "s|YOUR_PROJECT_PATH|$PROJECT_DIR|g" "$TEMPLATE" > "$GENERATED"
echo "Generated plist: $GENERATED"

# Create LaunchAgents directory if needed
mkdir -p "$LAUNCHD_DIR"

DEST_PLIST="$LAUNCHD_DIR/$SERVICE_NAME.plist"

# Unload if already loaded
if launchctl list | grep -q "$SERVICE_NAME"; then
    echo "Unloading existing service..."
    launchctl unload "$DEST_PLIST" 2>/dev/null || true
fi

# Copy plist to LaunchAgents
cp "$GENERATED" "$DEST_PLIST"
echo "Copied plist to: $DEST_PLIST"

# Load the service
launchctl load "$DEST_PLIST"
echo "Service loaded"

# Check status
echo
echo "Service status:"
launchctl list | grep "$SERVICE_NAME" || echo "Service not running yet"

echo
echo "Installation complete!"
echo
echo "Commands:"
echo "  Start:   launchctl start $SERVICE_NAME"
echo "  Stop:    launchctl stop $SERVICE_NAME"
echo "  Restart: launchctl kickstart -k gui/\$(id -u)/$SERVICE_NAME"
echo "  Logs:    tail -f $LOGS_DIR/jobradar.log"
echo "  Errors:  tail -f $LOGS_DIR/jobradar.error.log"
echo
echo "To uninstall:"
echo "  launchctl unload $DEST_PLIST"
echo "  rm $DEST_PLIST"
