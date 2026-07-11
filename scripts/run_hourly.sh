#!/bin/bash
# One scheduled InnoJobFinder run. Invoked by cron/systemd/launchd. Logs to logs/.
# Portable: the project root is derived from this script's location, and the
# `claude` CLI is expected on PATH (add ~/.local/bin if you installed it there).
set -u
PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$HOME/.local/bin:$PATH"

cd "$PROJECT" || exit 1
mkdir -p "$PROJECT/logs"
LOG="$PROJECT/logs/run_$(date +%Y%m%d).log"

{
  echo "===== run started $(date) ====="
  "$PROJECT/.venv/bin/python" -m jobfinder run
  # Capture before $(date) runs: command substitution overwrites $?.
  rc=$?
  echo "===== run finished $(date) (exit $rc) ====="
} >> "$LOG" 2>&1

# keep 14 days of logs
find "$PROJECT/logs" -name 'run_*.log' -mtime +14 -delete 2>/dev/null
exit 0
