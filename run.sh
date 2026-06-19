#!/usr/bin/env bash
# Determine the directory of this script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

# Activate the virtual environment
source "$DIR/venv/bin/activate"

# Run the agent with all arguments passed to this script
python3 "$DIR/agent.py" "$@"
