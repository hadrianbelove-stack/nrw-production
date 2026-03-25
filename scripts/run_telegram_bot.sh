#!/bin/bash
# Wrapper for launchd to run the Telegram bot with proper environment
LOG="/Users/hadrianbelove/Downloads/nrw-production/logs/telegram_bot_launch.log"
echo "=== Bot launch: $(date) ===" >> "$LOG"
echo "Python: $(/usr/bin/python3 --version 2>&1)" >> "$LOG"
cd /Users/hadrianbelove/Downloads/nrw-production || exit 1
exec /usr/bin/python3 -u nrw_telegram_bot.py >> "$LOG" 2>&1
