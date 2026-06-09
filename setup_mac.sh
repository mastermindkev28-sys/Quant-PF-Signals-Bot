#!/bin/bash
# PropBot Mac Setup Script
# Run this once: bash setup_mac.sh

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; exit 1; }
step()  { echo -e "\n${YELLOW}━━━ $1 ━━━${NC}"; }

echo ""
echo "╔══════════════════════════════════════╗"
echo "║      PropBot Mac Setup               ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ---------------------------------------------------------------
# 1. Homebrew
# ---------------------------------------------------------------
step "Checking Homebrew"
if ! command -v brew &>/dev/null; then
    # Check if we're in an interactive terminal — if not, guide the user
    if [ ! -t 0 ]; then
        echo ""
        echo "  ⚠  Cannot install Homebrew automatically (non-interactive mode)."
        echo ""
        echo "  Run this command in your Terminal window instead:"
        echo ""
        echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/homebrew/install/HEAD/install.sh)"'
        echo ""
        echo "  Then run this script again:  bash ~/setup_mac.sh"
        echo ""
        exit 1
    fi
    warn "Homebrew not found — installing (you may be asked for your Mac password)..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/homebrew/install/HEAD/install.sh)"
    # Add brew to PATH for Apple Silicon Macs
    if [[ $(uname -m) == "arm64" ]]; then
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
    info "Homebrew installed"
else
    info "Homebrew already installed"
fi

# ---------------------------------------------------------------
# 2. Python 3.11
# ---------------------------------------------------------------
step "Checking Python"
if command -v python3 &>/dev/null; then
    PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PY_MAJOR=$(echo $PY_VERSION | cut -d. -f1)
    PY_MINOR=$(echo $PY_VERSION | cut -d. -f2)
    if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 10 ]; then
        info "Python $PY_VERSION — good"
        PYTHON=python3
    else
        warn "Python $PY_VERSION too old — installing 3.11 via Homebrew"
        brew install python@3.11
        PYTHON=python3.11
    fi
else
    warn "Python not found — installing 3.11 via Homebrew"
    brew install python@3.11
    PYTHON=python3.11
fi

# ---------------------------------------------------------------
# 3. Git
# ---------------------------------------------------------------
step "Checking Git"
if ! command -v git &>/dev/null; then
    warn "Git not found — installing via Xcode tools"
    xcode-select --install || true
    info "Follow the popup to install Xcode Command Line Tools, then re-run this script"
    exit 0
else
    info "Git found"
fi

# ---------------------------------------------------------------
# 4. Clone or update repo
# ---------------------------------------------------------------
step "Setting up repository"
REPO_DIR="$HOME/PropBot"
if [ -d "$REPO_DIR/.git" ]; then
    info "Repo already exists at $REPO_DIR — pulling latest"
    cd "$REPO_DIR"
    git fetch origin
    git checkout claude/trademasteryos-futures-setup-5ug4p
    git pull origin claude/trademasteryos-futures-setup-5ug4p
else
    info "Cloning into $REPO_DIR"
    git clone https://github.com/mastermindkev28-sys/Quant-PF-Signals-Bot "$REPO_DIR"
    cd "$REPO_DIR"
    git checkout claude/trademasteryos-futures-setup-5ug4p
fi

# ---------------------------------------------------------------
# 5. Python virtual environment
# ---------------------------------------------------------------
step "Creating Python virtual environment"
cd "$REPO_DIR"
if [ ! -d "venv" ]; then
    $PYTHON -m venv venv
    info "Virtual environment created"
else
    info "Virtual environment already exists"
fi

source venv/bin/activate
info "Virtual environment activated"

# ---------------------------------------------------------------
# 6. Install dependencies
# ---------------------------------------------------------------
step "Installing Python packages"
pip install --upgrade pip --quiet
pip install -r prop_bot/requirements.txt --quiet
info "All packages installed"

# ---------------------------------------------------------------
# 7. Create .env file
# ---------------------------------------------------------------
step "Setting up environment file"
if [ ! -f ".env" ]; then
    cat > .env << 'ENVEOF'
# PropBot Environment Variables
# Fill in TELEGRAM_TOKEN and TELEGRAM_CHAT_ID to enable alerts
# Leave Tradovate blank for now — only needed for live trading

TELEGRAM_TOKEN=
TELEGRAM_CHAT_ID=

TRADOVATE_CID=
TRADOVATE_SECRET=
TRADOVATE_USERNAME=
TRADOVATE_PASSWORD=

ACCOUNT_SIZE=50000
ENVEOF
    info ".env file created — edit it to add your Telegram token"
else
    info ".env already exists"
fi

# ---------------------------------------------------------------
# 8. Create results directory
# ---------------------------------------------------------------
mkdir -p prop_bot/results prop_bot/data/cache
info "Results directories ready"

# ---------------------------------------------------------------
# 9. Create run scripts for easy launching
# ---------------------------------------------------------------
step "Creating launch shortcuts"

cat > "$REPO_DIR/backtest_nq.sh" << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
python prop_bot/main_backtest.py \
  --instrument NQ \
  --strategy dual_thrust \
  --start 2020-01-01 --end 2025-01-01 \
  --prop apex_50k \
  --config prop_bot/fast_pass_config.yaml \
  --monte-carlo --plot
EOF

cat > "$REPO_DIR/backtest_ibs_gold.sh" << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
python prop_bot/main_backtest.py \
  --instrument MGC \
  --strategy ibs \
  --start 2015-01-01 --end 2025-01-01 \
  --prop apex_50k \
  --monte-carlo --plot
EOF

cat > "$REPO_DIR/run_tests.sh" << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
python -m pytest prop_bot/tests/ -v
EOF

chmod +x "$REPO_DIR/backtest_nq.sh" "$REPO_DIR/backtest_ibs_gold.sh" "$REPO_DIR/run_tests.sh"
info "Launch scripts created"

# ---------------------------------------------------------------
# 10. Quick smoke test
# ---------------------------------------------------------------
step "Running smoke test"
cd "$REPO_DIR"
python -c "
import sys
sys.path.insert(0, '.')
from prop_bot.config import BotConfig, INSTRUMENTS, PROP_PRESETS
from prop_bot.indicators.ibs import compute_ibs_bands
import numpy as np, pandas as pd
cfg = BotConfig()
print('  Config OK')
print(f'  Instruments: {list(INSTRUMENTS.keys())}')
print(f'  Presets:     {list(PROP_PRESETS.keys())}')
print('  Import test passed')
"
info "Smoke test passed"

# ---------------------------------------------------------------
# Done
# ---------------------------------------------------------------
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  Setup complete! PropBot is ready at:                ║"
echo "║  $HOME/PropBot                                       ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  Next steps:                                         ║"
echo "║                                                      ║"
echo "║  1. Run backtest (NQ fast-pass):                     ║"
echo "║     bash ~/PropBot/backtest_nq.sh                    ║"
echo "║                                                      ║"
echo "║  2. Run backtest (IBS gold):                         ║"
echo "║     bash ~/PropBot/backtest_ibs_gold.sh              ║"
echo "║                                                      ║"
echo "║  3. Set up Telegram alerts:                          ║"
echo "║     Edit ~/PropBot/.env                              ║"
echo "║                                                      ║"
echo "║  Results saved to: ~/PropBot/prop_bot/results/       ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
