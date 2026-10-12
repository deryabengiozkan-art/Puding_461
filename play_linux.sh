#!/bin/sh
game_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -x "$game_dir/.venv/bin/python" ]; then
    exec "$game_dir/.venv/bin/python" "$game_dir/launch_game.py" "$@"
fi
for candidate in python3.11 python3.12 python3.10 python3.9 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
        exec "$candidate" "$game_dir/launch_game.py" "$@"
    fi
done
printf 'Install Python 3.11 with its venv package, then run this script again.\n'
exit 1
