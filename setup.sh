#!/usr/bin/env bash
# ============================================================
# Claude Code Mobile – one-shot setup script
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

info()  { echo -e "\033[0;36m[INFO]\033[0m  $*"; }
ok()    { echo -e "\033[0;32m[OK]\033[0m    $*"; }
warn()  { echo -e "\033[0;33m[WARN]\033[0m  $*"; }
error() { echo -e "\033[0;31m[ERROR]\033[0m $*" >&2; exit 1; }

# ------------------------------------------------------------
# 1. Check prerequisites
# ------------------------------------------------------------
info "Checking prerequisites…"
for cmd in python3 pip node npm claude; do
    if ! command -v "$cmd" &>/dev/null; then
        case "$cmd" in
            claude) warn "'claude' not found on PATH – make sure Claude Code CLI is installed" ;;
            *)      error "'$cmd' is required but not found" ;;
        esac
    else
        ok "$cmd found: $(command -v "$cmd")"
    fi
done

# ------------------------------------------------------------
# 2. Create .env if missing
# ------------------------------------------------------------
if [[ ! -f .env ]]; then
    info "Creating .env from .env.example…"
    cp .env.example .env
    # Generate a random AUTH_SECRET
    if command -v openssl &>/dev/null; then
        SECRET=$(openssl rand -hex 32)
    else
        SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    fi
    sed -i "s/^AUTH_SECRET=.*/AUTH_SECRET=${SECRET}/" .env
    ok ".env created with random AUTH_SECRET: ${SECRET}"
    warn "Save this secret – you'll need it to log in from your phone"
else
    info ".env already exists, skipping"
fi

# ------------------------------------------------------------
# 3. Backend – Python venv + deps
# ------------------------------------------------------------
info "Setting up Python virtual environment…"
if [[ ! -d .venv ]]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r backend/requirements.txt
ok "Python dependencies installed"

# ------------------------------------------------------------
# 4. Frontend – npm deps
# ------------------------------------------------------------
info "Installing frontend dependencies…"
cd frontend
npm install --silent
ok "Node dependencies installed"

# Build the frontend
info "Building frontend…"
npm run build
ok "Frontend built → frontend/dist/"
cd ..

# ------------------------------------------------------------
# 5. Print start instructions
# ------------------------------------------------------------
echo ""
echo -e "\033[1;35m====================================================\033[0m"
echo -e "\033[1;35m  Claude Code Mobile – Setup complete!\033[0m"
echo -e "\033[1;35m====================================================\033[0m"
echo ""

# Detect Tailscale IP
TAILSCALE_IP=""
if command -v tailscale &>/dev/null; then
    TAILSCALE_IP=$(tailscale ip -4 2>/dev/null | head -1 || true)
fi

if [[ -n "$TAILSCALE_IP" ]]; then
    echo -e "  Tailscale IP:   \033[1;32m${TAILSCALE_IP}\033[0m"
    echo -e "  Backend URL:    \033[1;34mhttp://${TAILSCALE_IP}:8000\033[0m"
    echo -e "  Frontend URL:   \033[1;34mhttp://${TAILSCALE_IP}:5173\033[0m  (dev)"
else
    warn "Tailscale not detected – use your machine IP manually"
fi

AUTH_SECRET=$(grep "^AUTH_SECRET=" .env | cut -d= -f2-)
echo ""
echo -e "  Auth Secret:    \033[1;33m${AUTH_SECRET}\033[0m"
echo ""
echo "  Start backend:  source .venv/bin/activate && uvicorn backend.main:app --host 0.0.0.0 --port 8000"
echo "  Start frontend: cd frontend && npm run dev -- --host"
echo ""
echo "  Or with Docker: docker compose up --build"
echo ""
