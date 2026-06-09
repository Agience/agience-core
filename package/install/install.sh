#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# Agience — Unified Install Script (Linux / macOS)
#
# One shot: installs Docker if needed, downloads the right docker-compose,
# pulls images, installs the `agience` CLI, starts the platform, and
# opens your browser.
#
# Modes:
#   home   — TLS via Caddy + custom domain (https://home.agience.ai).
#            Binds ports 80 + 443.
#   plain  — Bare HTTP at http://localhost:8080. No domain, no TLS.
#
# Channels:
#   stable — pulls released images (default)
#   edge   — pulls latest main-branch builds (VERSION=edge)
#
# Source: https://github.com/Agience/agience-core/blob/main/package/install/install.sh
#
# Usage:
#   curl -fsSL https://get.agience.ai/install.sh | sh -s -- --mode home
#   bash install.sh --mode plain --channel edge
#
# After install:
#   agience up      # start
#   agience down    # stop
#   agience update  # pull latest + restart
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Argument parsing ─────────────────────────────────────────────────

MODE="home"
CHANNEL="stable"

usage() {
    cat <<EOF
Usage: $0 [--mode home|plain] [--channel stable|edge]

Options:
  --mode      Deployment mode (default: home)
                home  — TLS + custom domain (home.agience.ai)
                plain — bare HTTP at localhost:8080
  --channel   Release channel (default: stable)
                stable — released images
                edge   — latest main-branch builds
  -h, --help  Show this help and exit
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --mode)
            MODE="${2:-}"; shift 2;;
        --mode=*)
            MODE="${1#--mode=}"; shift;;
        --channel)
            CHANNEL="${2:-}"; shift 2;;
        --channel=*)
            CHANNEL="${1#--channel=}"; shift;;
        -h|--help)
            usage; exit 0;;
        *)
            printf "Unknown argument: %s\n\n" "$1" >&2
            usage; exit 2;;
    esac
done

case "$MODE" in
    home|plain) ;;
    *) printf "Invalid --mode %q (expected: home, plain)\n" "$MODE" >&2; exit 2;;
esac

case "$CHANNEL" in
    stable|edge) ;;
    *) printf "Invalid --channel %q (expected: stable, edge)\n" "$CHANNEL" >&2; exit 2;;
esac

# ── Mode-dependent configuration ─────────────────────────────────────

REPO_RAW="https://raw.githubusercontent.com/Agience/agience-core/main/package/install"
COMPOSE_URL="${REPO_RAW}/${MODE}/docker-compose.yml"
INSTALL_DIR="${HOME}/.agience"
BIN_DIR="${HOME}/.local/bin"
COMPOSE_FILE="docker-compose.yml"
DOCKER_INSTALL_URL="https://get.docker.com"
DOCKER_DESKTOP_MAC_URL="https://www.docker.com/products/docker-desktop/"

if [ "$MODE" = "home" ]; then
    OPEN_URL="https://home.agience.ai"
    REQUIRED_PORTS="80 443"
    BANNER_LABEL="Agience — Install (home)"
    BANNER_DOMAIN="home.agience.ai"
else
    OPEN_URL="http://localhost:8080"
    REQUIRED_PORTS="8080"
    BANNER_LABEL="Agience — Install (plain)"
    BANNER_DOMAIN="http://localhost:8080"
fi

if [ "$CHANNEL" = "edge" ]; then
    BANNER_LABEL="${BANNER_LABEL} [edge]"
fi

# ── Colors (disabled if not a terminal) ──────────────────────────────

if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    RED='' GREEN='' YELLOW='' CYAN='' BOLD='' NC=''
fi

# ── Helpers ──────────────────────────────────────────────────────────

info()  { printf "${CYAN}[info]${NC}  %s\n" "$*"; }
ok()    { printf "${GREEN}[ok]${NC}    %s\n" "$*"; }
warn()  { printf "${YELLOW}[warn]${NC}  %s\n" "$*"; }
fail()  { printf "${RED}[error]${NC} %s\n" "$*" >&2; exit 1; }

command_exists() { command -v "$1" >/dev/null 2>&1; }

download() {
    local url=$1 dest=$2
    if command_exists curl; then
        curl -fsSL "$url" -o "$dest"
    elif command_exists wget; then
        wget -qO "$dest" "$url"
    else
        fail "Neither curl nor wget found. Cannot download files."
    fi
}

# ── Banner ───────────────────────────────────────────────────────────

printf "\n"
printf "${BOLD}  ============================================${NC}\n"
printf "${BOLD}  %s\n" "$BANNER_LABEL"
printf "${BOLD}  %s\n" "$BANNER_DOMAIN"
printf "${BOLD}  ============================================${NC}\n"
printf "\n"

# ── Step 1: Detect OS ────────────────────────────────────────────────

OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
    Linux)  PLATFORM="linux" ;;
    Darwin) PLATFORM="macos" ;;
    *)      fail "Unsupported operating system: $OS. This script supports Linux and macOS." ;;
esac

info "Detected: $OS ($ARCH); mode=$MODE channel=$CHANNEL"

# ── Step 2: Check / Install Docker ───────────────────────────────────

info "Checking for Docker..."

DOCKER_CMD="docker"
COMPOSE_CMD="docker compose"

install_docker_linux() {
    info "Docker not found. Installing Docker Engine (Community Edition)..."

    download "$DOCKER_INSTALL_URL" /tmp/get-docker.sh
    sh /tmp/get-docker.sh
    rm -f /tmp/get-docker.sh

    if command_exists systemctl; then
        sudo systemctl start docker
        sudo systemctl enable docker
    fi

    if ! groups | grep -q docker; then
        sudo usermod -aG docker "$USER"
        warn "Added $USER to the docker group."
        warn "You may need to log out and back in for group changes to take effect."
        DOCKER_CMD="sudo docker"
        COMPOSE_CMD="sudo docker compose"
        return
    fi
}

check_docker() {
    if ! command_exists docker; then
        return 1
    fi
    if ! docker info >/dev/null 2>&1; then
        if [ "$PLATFORM" = "linux" ] && sudo docker info >/dev/null 2>&1; then
            DOCKER_CMD="sudo docker"
            COMPOSE_CMD="sudo docker compose"
            return 0
        fi
        return 1
    fi
    return 0
}

if check_docker; then
    ok "Docker is installed and running"
else
    case "$PLATFORM" in
        linux)
            install_docker_linux
            if ! $DOCKER_CMD info >/dev/null 2>&1; then
                fail "Docker installation completed but the daemon is not responding. Try: sudo systemctl start docker"
            fi
            ok "Docker installed successfully"
            ;;
        macos)
            fail "Docker is not installed or not running.

  Install Docker using one of these options:

  Option 1 — Docker Desktop (recommended):
    ${DOCKER_DESKTOP_MAC_URL}

  Option 2 — Colima (free, lightweight):
    brew install colima docker docker-compose
    colima start

  After installing, start Docker and run this script again."
            ;;
    esac
fi

if ! $COMPOSE_CMD version >/dev/null 2>&1; then
    fail "Docker Compose (V2 plugin) not found. Install it: https://docs.docker.com/compose/install/"
fi

ok "Docker Compose available"

# ── Step 3: Check Port Conflicts ─────────────────────────────────────

info "Checking for port conflicts on: $REQUIRED_PORTS"

check_port() {
    local port=$1
    if [ "$PLATFORM" = "linux" ]; then
        if command_exists ss; then
            ss -tlnp 2>/dev/null | grep -q ":${port} " && return 0
        elif command_exists netstat; then
            netstat -tlnp 2>/dev/null | grep -q ":${port} " && return 0
        fi
    elif [ "$PLATFORM" = "macos" ]; then
        if command_exists lsof; then
            lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1 && return 0
        fi
    fi
    return 1
}

PORT_CONFLICTS=""
for p in $REQUIRED_PORTS; do
    if check_port "$p"; then
        PORT_CONFLICTS="${PORT_CONFLICTS} $p"
    fi
done

if [ -n "$PORT_CONFLICTS" ]; then
    fail "Required port(s) already in use:${PORT_CONFLICTS}

  Stop the service using these ports and re-run the installer.
  On macOS:   lsof -iTCP -sTCP:LISTEN | grep -E ':(${REQUIRED_PORTS// /|})\b'
  On Linux:   sudo ss -tlnp | grep -E ':(${REQUIRED_PORTS// /|})\b'

  Or install in plain mode (HTTP at localhost:8080) instead:
    bash install.sh --mode plain"
fi
ok "Required ports ($REQUIRED_PORTS) are available"

# ── Step 4: Create Install Directory ─────────────────────────────────

info "Install directory: $INSTALL_DIR"

if [ -d "$INSTALL_DIR" ] && [ -f "$INSTALL_DIR/$COMPOSE_FILE" ]; then
    warn "Existing installation found — updating and restarting"
else
    mkdir -p "$INSTALL_DIR"
    ok "Created $INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# ── Step 5: Download Compose File ────────────────────────────────────

info "Downloading compose configuration ($MODE)..."

download "$COMPOSE_URL" "$COMPOSE_FILE"

if [ ! -s "$COMPOSE_FILE" ]; then
    fail "Downloaded compose file is empty. Check your network and try again."
fi

ok "Compose file downloaded"

# ── Step 5b: Set release channel ─────────────────────────────────────

env_file="${INSTALL_DIR}/.env"
if [ "$CHANNEL" = "edge" ]; then
    if [ -f "$env_file" ]; then
        # Ensure trailing newline before parsing.
        [ -n "$(tail -c1 "$env_file")" ] && printf '\n' >> "$env_file"
        grep -v '^VERSION=' "$env_file" > "${env_file}.tmp" || true
        printf "VERSION=edge\n" >> "${env_file}.tmp"
        mv "${env_file}.tmp" "$env_file"
    else
        printf "VERSION=edge\n" > "$env_file"
    fi
    ok "Channel: edge"
else
    # Stable: drop any prior VERSION= line so the compose default applies.
    if [ -f "$env_file" ]; then
        grep -v '^VERSION=' "$env_file" > "${env_file}.tmp" || true
        if [ -s "${env_file}.tmp" ]; then
            mv "${env_file}.tmp" "$env_file"
        else
            rm -f "${env_file}.tmp" "$env_file"
        fi
    fi
    ok "Channel: stable"
fi

# ── Step 6: Pull Images ──────────────────────────────────────────────

info "Pulling container images (this may take a few minutes)..."
printf "\n"

# Retry on transient network failures. Three attempts, exponential backoff.
PULL_OK=false
for attempt in 1 2 3; do
    if $COMPOSE_CMD pull; then
        PULL_OK=true
        break
    fi
    if [ "$attempt" -lt 3 ]; then
        warn "Image pull failed (attempt ${attempt}/3). Retrying in $((attempt * 5))s..."
        sleep "$((attempt * 5))"
    fi
done

if ! $PULL_OK; then
    fail "Failed to pull container images after 3 attempts.

  Common causes:
    - Network connectivity / Docker Hub unreachable.
    - Tag does not exist (check VERSION in $env_file or .env).
    - Behind a proxy: set HTTP_PROXY / HTTPS_PROXY before re-running.

  Try: docker compose pull"
fi

printf "\n"
ok "All images pulled"

# ── Step 7: Install agience CLI ──────────────────────────────────────

info "Installing agience command..."

mkdir -p "$BIN_DIR"

cat > "${BIN_DIR}/agience" << AGIENCE_CLI
#!/usr/bin/env bash
# Agience runtime CLI — wraps docker compose against the user's install.
AGIENCE_DIR="\${HOME}/.agience"
OPEN_URL="${OPEN_URL}"
cd "\$AGIENCE_DIR" 2>/dev/null || { echo "Agience not found at \${AGIENCE_DIR}. Re-run the installer."; exit 1; }

# Every command needs Docker running.
require_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        echo "Docker is not installed. Install Docker Desktop and try again."
        exit 1
    fi
    if ! docker info >/dev/null 2>&1; then
        echo "Docker is installed but not running. Start Docker and try again."
        exit 1
    fi
}

cmd="\${1:-}"
case "\$cmd" in
    up)
        require_docker
        docker compose up -d
        echo ""
        echo "Agience is running. Open: \$OPEN_URL"
        ;;
    down)
        require_docker
        docker compose down
        ;;
    logs)
        require_docker
        shift
        docker compose logs -f "\$@"
        ;;
    update)
        require_docker
        docker compose pull
        docker compose up -d
        echo ""
        echo "Updated. Open: \$OPEN_URL"
        ;;
    status)
        require_docker
        docker compose ps
        ;;
    open)
        if command -v xdg-open >/dev/null 2>&1; then
            xdg-open "\$OPEN_URL" >/dev/null 2>&1 &
        elif command -v open >/dev/null 2>&1; then
            open "\$OPEN_URL"
        else
            echo "\$OPEN_URL"
        fi
        ;;
    setup-token)
        TOKEN_FILE="\${AGIENCE_DIR}/.data/keys/setup.token"
        if [ -f "\$TOKEN_FILE" ]; then
            cat "\$TOKEN_FILE" 2>/dev/null || sudo cat "\$TOKEN_FILE"
        else
            echo "No setup token at \$TOKEN_FILE. Setup may already be complete."
            exit 1
        fi
        ;;
    reset)
        require_docker
        echo "This will STOP Agience and DELETE all data at \$AGIENCE_DIR/.data/"
        echo "A timestamped backup will be made at \$AGIENCE_DIR/.data.backup-<ts>"
        printf "Type 'reset' to continue: "
        read -r confirm
        if [ "\$confirm" != "reset" ]; then
            echo "Cancelled."
            exit 1
        fi
        docker compose down -v 2>/dev/null || true
        if [ -d "\$AGIENCE_DIR/.data" ]; then
            ts=\$(date +%Y%m%d-%H%M%S)
            mv "\$AGIENCE_DIR/.data" "\$AGIENCE_DIR/.data.backup-\$ts"
            echo "Backed up old data to \$AGIENCE_DIR/.data.backup-\$ts"
        fi
        echo "Reset complete. Run 'agience up' to start fresh."
        ;;
    version|--version|-v)
        if [ -f "\$AGIENCE_DIR/.env" ] && grep -q '^VERSION=' "\$AGIENCE_DIR/.env"; then
            grep '^VERSION=' "\$AGIENCE_DIR/.env"
        else
            echo "VERSION=stable (default)"
        fi
        ;;
    *)
        cat <<USAGE
Usage: agience <command>

Commands:
  up            Start Agience.
  down          Stop Agience.
  logs [svc]    Tail logs (optionally for one service).
  update        Pull latest images and restart.
  status        Show running containers.
  open          Open Agience in your browser.
  setup-token   Print the first-boot setup token (if not yet consumed).
  reset         Stop + back up data dir + start fresh.
  version       Show the configured channel/version.

URL: \$OPEN_URL
USAGE
        exit 1
        ;;
esac
AGIENCE_CLI

chmod +x "${BIN_DIR}/agience"
ok "agience CLI installed to ${BIN_DIR}/agience"

# Add ~/.local/bin to PATH if not already present.
PATH_UPDATED=false
if ! echo "$PATH" | tr ':' '\n' | grep -qx "$BIN_DIR"; then
    PATH_LINE="export PATH=\"\$PATH:${BIN_DIR}\""
    for rc in "${HOME}/.bashrc" "${HOME}/.zshrc" "${HOME}/.profile"; do
        if [ -f "$rc" ]; then
            if ! grep -qF "$BIN_DIR" "$rc" 2>/dev/null; then
                printf '\n# Added by Agience installer\n%s\n' "$PATH_LINE" >> "$rc"
            fi
        fi
    done
    export PATH="$PATH:${BIN_DIR}"
    PATH_UPDATED=true
fi

# ── Step 8: Start ────────────────────────────────────────────────────

info "Starting Agience..."
$COMPOSE_CMD up -d
ok "Agience is running"

# ── Read setup token ─────────────────────────────────────────────────

SETUP_TOKEN=""
TOKEN_FILE="${INSTALL_DIR}/.data/keys/setup.token"
if [ -f "$TOKEN_FILE" ]; then
    SETUP_TOKEN=$(cat "$TOKEN_FILE" 2>/dev/null || sudo cat "$TOKEN_FILE" 2>/dev/null || true)
fi

# ── Step 9: Open browser ─────────────────────────────────────────────

if command_exists xdg-open; then
    xdg-open "$OPEN_URL" >/dev/null 2>&1 &
elif command_exists open; then
    open "$OPEN_URL"
fi

# ── Done ─────────────────────────────────────────────────────────────

printf "\n"
printf "${BOLD}${GREEN}  ============================================${NC}\n"
printf "${BOLD}${GREEN}  Agience is running!${NC}\n"
printf "${BOLD}${GREEN}  ============================================${NC}\n"
printf "\n"
printf "  Open:     ${BOLD}%s${NC}\n" "$OPEN_URL"
printf "  Mode:     %s\n" "$MODE"
printf "  Channel:  %s\n" "$CHANNEL"
printf "  Data:     %s/.data/\n" "$INSTALL_DIR"
printf "\n"
if [ -n "$SETUP_TOKEN" ]; then
    printf "  ${YELLOW}Setup:    %s${NC}\n" "$SETUP_TOKEN"
    printf "\n"
fi
printf "  ${BOLD}Commands:${NC}\n"
printf "    agience up           start\n"
printf "    agience down         stop\n"
printf "    agience logs [svc]   tail logs\n"
printf "    agience update       pull latest images and restart\n"
printf "    agience status       show running containers\n"
printf "    agience open         open Agience in your browser\n"
printf "    agience setup-token  print first-boot setup token\n"
printf "    agience reset        back up data dir + start fresh\n"
printf "    agience version      show configured channel/version\n"
printf "\n"

if $PATH_UPDATED; then
    printf "  ${YELLOW}Note:${NC} Open a new terminal (or run ${BOLD}source ~/.bashrc${NC}) for 'agience' to be on your PATH.\n"
    printf "\n"
fi
