#!/bin/sh
game_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -x "$game_dir/.venv/bin/python" ]; then
    "$game_dir/.venv/bin/python" "$game_dir/launch_game.py" "$@"
    result=$?
else
    result=1
    for candidate in python3.11 python3.12 python3.10 python3.9 python3; do
        if command -v "$candidate" >/dev/null 2>&1; then
            "$candidate" "$game_dir/launch_game.py" "$@"
            result=$?
            break
        fi
    done
fi
if [ "$result" -ne 0 ]; then
    printf '\nIf Python was not found, install Python 3.11 from https://www.python.org/downloads/\n'
    printf 'Press Return to close this window.'
    read -r answer
fi
exit "$result"
