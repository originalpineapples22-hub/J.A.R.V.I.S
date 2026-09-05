#!/usr/bin/env bash
# 0.5.4.M.4 — one-click launcher for Linux and macOS.
#   ./start.sh
# Same checks as start.ps1: right folder, nothing shadowing the package,
# private environment, dependencies, then the server on port 8080.

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$root"

fail() { printf '\n  \033[31mX  %s\033[0m\n\n' "$1"; exit 1; }

printf '\n  \033[36m0.5.4.M.4  --  starting up\033[0m\n  \033[90m%s\033[0m\n\n' "$root"

[ -f "$root/jarvis/server.py" ] || fail "This folder is not the current version of 0.5.4.M.4.
     Expected $root/jarvis/server.py

     Get the current one:
       git clone -b claude/jarvis-self-learning-pfsxu0 https://github.com/originalpineapples22-hub/J.A.R.V.I.S.git jarvis-v3
       cd jarvis-v3 && ./start.sh

     If this IS the right folder, you are behind — run: git pull"

[ -f "$root/jarvis.py" ] && fail "A file called jarvis.py sits next to the jarvis/ folder.
     Python loads that instead of the package, so jarvis.server cannot be found.
     Move it:  mv '$root/jarvis.py' '$root/legacy/jarvis_old.py'"

py=""
for c in python3.13 python3.12 python3.11 python3 python; do
    command -v "$c" >/dev/null 2>&1 || continue
    if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
        py="$c"; break
    fi
done
[ -n "$py" ] || fail "Python 3.10 or newer was not found. Install it and run this again."
printf '  \033[90mpython: %s\033[0m\n' "$py"

venv="$root/.venv/bin/python"
if [ ! -x "$venv" ]; then
    printf '  \033[33mcreating a private Python environment (once)...\033[0m\n'
    "$py" -m venv "$root/.venv" || fail "Could not create .venv (on Debian/Ubuntu: sudo apt install python3-venv)"
fi

stamp="$root/.venv/.installed"
want="$("$venv" -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$root/requirements.txt")"
if [ ! -f "$stamp" ] || [ "$(cat "$stamp")" != "$want" ]; then
    printf '  \033[33minstalling dependencies (once, 2-5 min)...\033[0m\n'
    "$venv" -m pip install --upgrade pip --quiet
    "$venv" -m pip install -r "$root/requirements.txt" || fail "Dependency install failed — the reason is above."
    # extras are best-effort: a missing one only turns off its own feature
    "$venv" -m pip install -r "$root/requirements-optional.txt" >/dev/null 2>&1 || true
    printf '%s' "$want" > "$stamp"
fi

if [ ! -f "$root/.env" ] && [ -f "$root/.env.example" ]; then
    cp "$root/.env.example" "$root/.env"
    printf '\n  \033[33mCreated .env — add a free brain key to it when you have one.\033[0m\n'
fi

if ! out="$("$venv" -c 'import jarvis.server' 2>&1)"; then
    printf '\n\033[90m%s\033[0m\n' "$out"
    fail "0.5.4.M.4 could not load. The real reason is the last line above."
fi

if [ -f "$root/.env" ] && grep -q '^JARVIS_TOKEN=choose-a-long-secret' "$root/.env"; then
    sed -i.bak 's/^JARVIS_TOKEN=choose-a-long-secret/# JARVIS_TOKEN was the example placeholder — removed, a strong one is generated/' "$root/.env"
    rm -f "$root/.env.bak"
    printf '  \033[33mremoved the placeholder token from .env — using a generated one\033[0m\n'
fi
token="$("$venv" -m jarvis.showtoken)"
printf '\n  ------------------------------------------------------------\n'
printf '   \033[32mOpen:  http://localhost:8080\033[0m\n'
printf '   \033[32mToken: %s\033[0m\n' "$token"
printf '  ------------------------------------------------------------\n'
printf '   \033[90mStop it with Ctrl+C.\033[0m\n\n'

args=(--host 0.0.0.0 --port 8080)
[ -f "$root/.env" ] && args+=(--env-file "$root/.env")
exec "$venv" -m uvicorn jarvis.server:app "${args[@]}"
