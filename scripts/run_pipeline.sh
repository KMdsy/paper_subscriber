#!/bin/bash

# ============================================================
# Paper Subscriber Automation Pipeline
# This script runs the fetching process and syncs results to GitHub.
# Designed for cron jobs / scheduled tasks.
# ============================================================

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Navigation to project root
cd "$PROJECT_ROOT" || { echo "❌ Critical: Could not change directory to $PROJECT_ROOT"; exit 1; }

echo "🚀 Starting Pipeline: $(date)"

# 1. Check for .venv
if [ ! -d ".venv" ]; then
    echo "❌ Error: .venv directory not found in $PROJECT_ROOT"
    exit 1
fi

PYTHON_BIN=".venv/bin/python3"

# 2. Run Fetch and Process
echo "📥 Step 1: Fetching and processing papers..."
if $PYTHON_BIN scripts/fetch_and_process.py; then
    echo "✅ Fetching completed successfully."
else
    echo "⚠️ Warning: fetch_and_process.py encountered an error, but proceeding to sync..."
    # We continue to sync even if some papers failed, so we don't lose the successful ones
fi

# 3. Sync to GitHub
echo "📤 Step 2: Syncing to GitHub..."
if $PYTHON_BIN scripts/sync_github.py; then
    echo "✅ GitHub sync completed successfully."
else
    echo "❌ Error: GitHub sync failed."
    exit 1
fi

echo "🎉 Pipeline finished successfully at $(date)"
echo "------------------------------------------------------------"
