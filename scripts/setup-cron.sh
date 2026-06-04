#!/bin/bash
# Setup cron job for automated backups
# Run once: ./setup-cron.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_SCRIPT="$SCRIPT_DIR/backup-db.sh"

echo "Setting up backup cron job..."
echo "Schedule: Daily at 3:00 AM"
echo "Script: $BACKUP_SCRIPT"
echo ""

# Remove existing flowmanner backup entries
(crontab -l 2>/dev/null | grep -v "flowmanner.*backup") | crontab - 2>/dev/null || true

# Add new entry
(crontab -l 2>/dev/null; echo "0 3 * * * $BACKUP_SCRIPT >> /opt/flowmanner/backups/cron.log 2>&1") | crontab -

echo "Cron job installed. Current crontab:"
crontab -l | grep flowmanner
echo ""
echo "Logs: /opt/flowmanner/backups/cron.log"
