#!/bin/bash
# Setup script for Ubuntu cron deployment (with venv support)

SCRIPT_DIR="/home/amir/controller"
LOG_DIR="$SCRIPT_DIR/logs"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python3"

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Ensure logs directory is writable
chmod 755 "$LOG_DIR"

# Check if venv exists
if [ ! -f "$VENV_PYTHON" ]; then
    echo "Error: venv not found at $SCRIPT_DIR/venv"
    echo "Please create venv first: python3 -m venv venv"
    exit 1
fi

# Install Python dependencies in venv
"$VENV_PYTHON" -m pip install -r "$SCRIPT_DIR/requirements.txt"

# Add cron job (runs every 10 minutes, uses venv Python)
(crontab -l 2>/dev/null | grep -v "flow-controller\|melcloud_flow_controller"; echo "*/10 * * * * cd $SCRIPT_DIR && $VENV_PYTHON melcloud_flow_controller.py >> $LOG_DIR/cron.log 2>&1") | crontab -

echo "Setup complete!"
echo "Logs directory: $LOG_DIR"
echo "CSV log: $LOG_DIR/heating_log.csv"
echo "Cron log: $LOG_DIR/cron.log"
echo "Using venv Python: $VENV_PYTHON"
echo ""
echo "To view cron log: tail -f $LOG_DIR/cron.log"
echo "To check cron jobs: crontab -l"

