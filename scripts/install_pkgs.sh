#!/bin/bash
# Runs automatically at the start of each Claude Code session to prepare
# the fresh sandbox. Safe to run before requirements.txt exists.
set -e

if [ -f requirements.txt ]; then
  pip install -r requirements.txt
fi

exit 0
