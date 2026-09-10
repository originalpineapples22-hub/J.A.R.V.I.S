#!/usr/bin/env bash
# 0.5.4.M.4 — install a brain that is yours. Mac and Linux.
#   ./deploy/local_brain.sh
set -u
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
say() { printf '  %s\n' "$1"; }

printf '\n  \033[36m0.5.4.M.4  --  installing your own brain\033[0m\n\n'

if [ "$(uname -s)" = "Darwin" ]; then
    ram=$(( $(sysctl -n hw.memsize) / 1073741824 ))
else
    ram=$(( $(awk '/MemTotal/ {print $2}' /proc/meminfo) / 1048576 ))
fi
say "memory: ${ram} GB RAM"
if   [ "$ram" -ge 32 ]; then model="qwen2.5-coder:14b"; size="9 GB"
elif [ "$ram" -ge 16 ]; then model="qwen2.5-coder:7b";  size="4.7 GB"
elif [ "$ram" -ge 8  ]; then model="qwen2.5:3b";        size="1.9 GB"
else                         model="qwen2.5:1.5b";      size="1 GB"
fi
printf '  \033[32mchosen: %s (about %s to download)\033[0m\n\n' "$model" "$size"

if ! command -v ollama >/dev/null 2>&1; then
    printf '  \033[33minstalling ollama...\033[0m\n'
    if [ "$(uname -s)" = "Darwin" ] && command -v brew >/dev/null 2>&1; then
        brew install ollama && brew services start ollama
    else
        curl -fsSL https://ollama.com/install.sh | sh
    fi
fi
command -v ollama >/dev/null 2>&1 || { printf '\n  \033[31mX  Install ollama from https://ollama.com/download, then run this again.\033[0m\n\n'; exit 1; }

printf '  \033[33mdownloading %s - the only big download, and it is once.\033[0m\n' "$model"
ollama pull "$model" || { printf '\n  \033[31mX  Download failed.\033[0m\n\n'; exit 1; }
say "it said: $(ollama run "$model" 'Reply with exactly: online' 2>&1 | head -1)"

py="$root/.venv/bin/python"; [ -x "$py" ] || py=python3
"$py" -c "
import sys; sys.path.insert(0, '$root')
from jarvis.config import save_settings
save_settings({'use_ollama': True, 'prefer_local': True,
               'ollama_model': '$model', 'ollama_url': 'http://localhost:11434'})
print('  pointed the assistant at it')
" || say "could not write settings - turn on Ollama in Settings yourself"

printf '\n  ------------------------------------------------------------\n'
printf '   \033[32mYour brain is installed and set as first choice.\033[0m\n'
printf '   \033[32m%s, on this machine. No key, no quota, works offline.\033[0m\n' "$model"
printf '  ------------------------------------------------------------\n\n'
