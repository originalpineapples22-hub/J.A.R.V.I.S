#!/usr/bin/env bash
# 0.5.4.M.4 — give the local server a public HTTPS address, for Mac and Linux.
# Run ./start.sh in one terminal, then ./tunnel.sh in a second.

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$root"
port=8080

fail() { printf '\n  \033[31mX  %s\033[0m\n\n' "$1"; exit 1; }

printf '\n  \033[36m0.5.4.M.4  --  opening a public address\033[0m\n\n'

if ! (exec 3<>/dev/tcp/127.0.0.1/$port) 2>/dev/null; then
    fail "Nothing is listening on port $port.
     Run ./start.sh in another terminal, wait for \"Uvicorn running\",
     leave it open, then run this again."
fi
printf '  \033[90mserver: running on port %s\033[0m\n' "$port"

exe="$(command -v cloudflared || true)"
if [ -z "$exe" ]; then
    exe="$root/.bin/cloudflared"
    if [ ! -x "$exe" ]; then
        mkdir -p "$root/.bin"
        case "$(uname -s)-$(uname -m)" in
            Darwin-arm64)        asset=cloudflared-darwin-arm64.tgz ;;
            Darwin-x86_64)       asset=cloudflared-darwin-amd64.tgz ;;
            Linux-x86_64)        asset=cloudflared-linux-amd64 ;;
            Linux-aarch64|Linux-arm64) asset=cloudflared-linux-arm64 ;;
            *) fail "No prebuilt cloudflared for $(uname -s)-$(uname -m). Install it from cloudflare.com/products/tunnel" ;;
        esac
        url="https://github.com/cloudflare/cloudflared/releases/latest/download/$asset"
        printf '  \033[33mdownloading cloudflared (once, ~20 MB)...\033[0m\n'
        case "$asset" in
            *.tgz) curl -fsSL "$url" | tar -xz -C "$root/.bin" cloudflared || fail "Download failed. Try: brew install cloudflared" ;;
            *)     curl -fsSL "$url" -o "$exe" || fail "Download failed: $url" ;;
        esac
        chmod +x "$exe" 2>/dev/null || true
    fi
    [ -x "$exe" ] || fail "cloudflared did not download. Install it by hand from cloudflare.com/products/tunnel"
fi
printf '  \033[90mcloudflared: %s\033[0m\n\n' "$exe"

printf '  \033[32mWatch for a line like  https://something.trycloudflare.com\033[0m\n'
printf '  \033[90mOpen that on your phone and paste your token. Ctrl+C to stop.\033[0m\n'
printf '  \033[90mThe address changes every time you restart this.\033[0m\n\n'

exec "$exe" tunnel --url "http://localhost:$port"
