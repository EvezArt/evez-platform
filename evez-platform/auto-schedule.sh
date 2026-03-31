#!/bin/bash
# EVEZ Auto-Scheduler — Sets up cron jobs for autonomous operation
# Runs income scans, market observation, git commits, and health checks

echo "⚡ EVEZ Auto-Scheduler"

# Income scan every 30 minutes
(crontab -l 2>/dev/null; echo "*/30 * * * * curl -s -X POST http://localhost:8080/api/income/scan > /dev/null 2>&1") | sort -u | crontab -

# Market observation every 15 minutes
(crontab -l 2>/dev/null; echo "*/15 * * * * curl -s -X POST http://localhost:8080/api/finance/observe > /dev/null 2>&1") | sort -u | crontab -

# Health check every 5 minutes
(crontab -l 2>/dev/null; echo "*/5 * * * * curl -s http://localhost:8080/api/health > /dev/null 2>&1") | sort -u | crontab -

# Memory decay every hour
(crontab -l 2>/dev/null; echo "0 * * * * curl -s http://localhost:8080/api/memory > /dev/null 2>&1") | sort -u | crontab -

echo "Cron jobs installed:"
crontab -l 2>/dev/null | grep -v "^#"
echo ""
echo "⚡ Auto-scheduling active"
