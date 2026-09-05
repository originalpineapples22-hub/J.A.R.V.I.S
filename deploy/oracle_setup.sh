#!/usr/bin/env bash
# One-shot installer for 0.5.4.M.4 on an Oracle Cloud Always-Free Ubuntu VM
# (or any Ubuntu/Debian server).
#
#   curl -fsSL https://raw.githubusercontent.com/originalpineapples22-hub/J.A.R.V.I.S/claude/jarvis-self-learning-pfsxu0/deploy/oracle_setup.sh | bash
#
# Core packages must succeed; optional ones are best-effort so a single
# awkward dependency can never abort the whole installation.
set -euo pipefail
REPO="https://github.com/originalpineapples22-hub/J.A.R.V.I.S.git"
BRANCH="claude/jarvis-self-learning-pfsxu0"
DIR="$HOME/jarvis"
BOLD=$'\e[1m'; DIM=$'\e[2m'; OK=$'\e[32m'; WARN=$'\e[33m'; NC=$'\e[0m'

echo "${BOLD}==> [1/6] System packages${NC}"
sudo apt-get update -y
# build-essential + python3-dev are REQUIRED: pywebpush compiles C extensions.
# ffmpeg lets yt-dlp read social video audio.
sudo apt-get install -y python3 python3-venv python3-pip python3-dev \
    build-essential libffi-dev git curl ffmpeg \
    debian-keyring debian-archive-keyring apt-transport-https

echo "${BOLD}==> [2/6] Fetching 0.5.4.M.4${NC}"
if [ -d "$DIR/.git" ]; then git -C "$DIR" pull; else git clone -b "$BRANCH" "$REPO" "$DIR"; fi
cd "$DIR"
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip wheel setuptools

echo "${BOLD}==> [3/6] Core dependencies${NC}"
pip install -r requirements.txt

echo "${BOLD}==> [4/6] Optional extras ${DIM}(failures here are safe)${NC}"
FAILED=""
while read -r line; do
  pkg="${line%%#*}"; pkg="$(echo "$pkg" | xargs)"
  [ -z "$pkg" ] && continue
  echo "    · $pkg"
  pip install "$pkg" >/tmp/opt.log 2>&1 || { FAILED="$FAILED $pkg"; echo "      ${WARN}skipped (not fatal)${NC}"; }
done < requirements-optional.txt
python -c "import playwright" 2>/dev/null && (playwright install --with-deps chromium >/dev/null 2>&1 || true)
[ -n "$FAILED" ] && echo "    ${WARN}Not installed:$FAILED — the matching features simply stay off.${NC}"

echo "${BOLD}==> [5/6] Configuration${NC}"
if [ ! -f .env ]; then
  echo "${DIM}Free keys — press Enter to skip any you do not have yet.${NC}"
  read -rp "  Groq API key        (console.groq.com)          : " GROQ || true
  read -rp "  GitHub Models token (github.com/settings/tokens): " GHKEY || true
  read -rp "  Google Gemini key   (aistudio.google.com/apikey): " GEMKEY || true
  TOKEN=$(python3 -c "import secrets;print(secrets.token_urlsafe(18))")
  cat > .env <<ENV
GROQ_API_KEY=${GROQ:-}
JARVIS_TOKEN=$TOKEN
JARVIS_TZ=Asia/Muscat
PORT=8080
ENV
  mkdir -p data
  python3 - <<PY
import json, pathlib
s = {}
for k, v in (("github_models_key", "${GHKEY:-}"), ("gemini_key", "${GEMKEY:-}"), ("groq_api_key", "${GROQ:-}")):
    if v.strip():
        s[k] = v.strip()
if s:
    p = pathlib.Path("data/settings.json")
    cur = json.loads(p.read_text()) if p.exists() else {}
    cur.update(s)
    p.write_text(json.dumps(cur, indent=2))
    print("    keys stored")
PY
fi
ACCESS_TOKEN=$(grep '^JARVIS_TOKEN=' .env | cut -d= -f2-)

echo "${BOLD}==> [6/6] HTTPS and service${NC}"
read -rp "  DuckDNS subdomain (e.g. mohamedjarvis), blank to skip HTTPS: " DUCK || true
BIND="0.0.0.0"          # reachable directly when there is no reverse proxy
if [ -n "${DUCK:-}" ]; then
  read -rp "  DuckDNS token: " DUCKTOK
  PUBIP=$(curl -s https://api.ipify.org)
  curl -s "https://www.duckdns.org/update?domains=$DUCK&token=$DUCKTOK&ip=$PUBIP" >/dev/null && echo "    DuckDNS → $PUBIP"
  (crontab -l 2>/dev/null | grep -v duckdns.org; echo "*/10 * * * * curl -s 'https://www.duckdns.org/update?domains=$DUCK&token=$DUCKTOK&ip=' >/dev/null") | crontab -
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --batch --yes --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  sudo apt-get update -y && sudo apt-get install -y caddy
  sudo tee /etc/caddy/Caddyfile >/dev/null <<CADDY
$DUCK.duckdns.org {
    reverse_proxy 127.0.0.1:8080
}
CADDY
  sudo systemctl restart caddy
  BIND="127.0.0.1"      # Caddy fronts it; keep the app off the public interface
  sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT 2>/dev/null || true
  sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT 2>/dev/null || true
  sudo netfilter-persistent save 2>/dev/null || true
  URL="https://$DUCK.duckdns.org"
else
  sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8080 -j ACCEPT 2>/dev/null || true
  sudo netfilter-persistent save 2>/dev/null || true
  URL="http://$(curl -s https://api.ipify.org):8080"
fi

sudo tee /etc/systemd/system/jarvis.service >/dev/null <<UNIT
[Unit]
Description=0.5.4.M.4 core
After=network.target
[Service]
WorkingDirectory=$DIR
EnvironmentFile=$DIR/.env
ExecStart=$DIR/.venv/bin/uvicorn jarvis.server:app --host $BIND --port 8080
Restart=always
RestartSec=5
User=$USER
[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now jarvis
sleep 6

echo
if curl -fsS "http://127.0.0.1:8080/api/health" >/dev/null 2>&1; then
  echo "${OK}${BOLD}✅ 0.5.4.M.4 is running.${NC}"
else
  echo "${WARN}⚠️  The service did not answer yet. Check:  journalctl -u jarvis -n 40 --no-pager${NC}"
fi
echo
echo "   Address:      ${BOLD}$URL${NC}"
echo "   Access token: ${BOLD}$ACCESS_TOKEN${NC}"
echo "   ${DIM}(shown again any time with:  grep JARVIS_TOKEN ~/jarvis/.env)${NC}"
echo
echo "   Open the address, press ⚙, paste the token, then type: ${BOLD}system check${NC}"
