#!/usr/bin/env bash
# One-shot installer for an Oracle Cloud Always-Free Ubuntu VM (or any Ubuntu/Debian server).
# Usage (on the server):  curl -fsSL https://raw.githubusercontent.com/originalpineapples22-hub/J.A.R.V.I.S/claude/jarvis-self-learning-pfsxu0/deploy/oracle_setup.sh | bash
set -e
REPO="https://github.com/originalpineapples22-hub/J.A.R.V.I.S.git"
BRANCH="claude/jarvis-self-learning-pfsxu0"
DIR="$HOME/jarvis"

echo "==> Installing system packages"
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip git curl debian-keyring debian-archive-keyring apt-transport-https

echo "==> Getting J.A.R.V.I.S."
if [ -d "$DIR/.git" ]; then git -C "$DIR" pull; else git clone -b "$BRANCH" "$REPO" "$DIR"; fi
cd "$DIR"
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Configuration"
if [ ! -f .env ]; then
  read -rp "Groq API key (console.groq.com): " GROQ
  TOKEN=$(python3 -c "import secrets;print(secrets.token_urlsafe(18))")
  cat > .env <<ENV
GROQ_API_KEY=$GROQ
JARVIS_TOKEN=$TOKEN
JARVIS_TZ=Asia/Muscat
PORT=8080
ENV
  echo "Your operator access token is: $TOKEN   (saved in $DIR/.env — you will paste it into the app once)"
fi

echo "==> systemd service"
sudo tee /etc/systemd/system/jarvis.service >/dev/null <<UNIT
[Unit]
Description=J.A.R.V.I.S. core
After=network.target
[Service]
WorkingDirectory=$DIR
EnvironmentFile=$DIR/.env
ExecStart=$DIR/.venv/bin/uvicorn jarvis.server:app --host 127.0.0.1 --port 8080
Restart=always
User=$USER
[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now jarvis

echo "==> HTTPS (needed for the app to install on iPhone and for notifications)"
read -rp "Your DuckDNS subdomain (e.g. myjarvis  → myjarvis.duckdns.org), or blank to skip: " DUCK
if [ -n "$DUCK" ]; then
  read -rp "DuckDNS token: " DUCKTOK
  PUBIP=$(curl -s https://api.ipify.org)
  curl -s "https://www.duckdns.org/update?domains=$DUCK&token=$DUCKTOK&ip=$PUBIP" >/dev/null && echo "DuckDNS updated to $PUBIP"
  (crontab -l 2>/dev/null; echo "*/10 * * * * curl -s 'https://www.duckdns.org/update?domains=$DUCK&token=$DUCKTOK&ip=' >/dev/null") | crontab -
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  sudo apt-get update -y && sudo apt-get install -y caddy
  sudo tee /etc/caddy/Caddyfile >/dev/null <<CADDY
$DUCK.duckdns.org {
    reverse_proxy 127.0.0.1:8080
}
CADDY
  sudo systemctl restart caddy
  # Oracle VMs also need ports 80/443 opened in the VCN security list AND in the OS firewall:
  sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
  sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
  sudo netfilter-persistent save 2>/dev/null || true
  echo "==> J.A.R.V.I.S. is live at https://$DUCK.duckdns.org"
else
  echo "==> J.A.R.V.I.S. is running on port 8080 (HTTP only). Rerun with DuckDNS for HTTPS."
fi
