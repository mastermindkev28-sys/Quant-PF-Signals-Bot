#!/bin/bash
# Interactive Telegram alert setup for PropBot
# Run: bash setup_telegram.sh

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║      PropBot Telegram Alert Setup        ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"
echo ""

# ---------------------------------------------------------------
# Step 1: Get token from user
# ---------------------------------------------------------------
echo -e "${YELLOW}STEP 1 — Create your Telegram bot${NC}"
echo ""
echo "  1. Open Telegram and search for: @BotFather"
echo "  2. Send this message to BotFather:  /newbot"
echo "  3. Give it any name (e.g. 'My PropBot')"
echo "  4. Give it a username ending in 'bot' (e.g. 'mypropbot_alerts_bot')"
echo "  5. BotFather will send you a token like:"
echo "     1234567890:ABCDefghijklmnopqrstuvwxyz"
echo ""
read -p "  Paste your bot token here: " BOT_TOKEN

if [ -z "$BOT_TOKEN" ]; then
    echo "No token entered. Exiting."
    exit 1
fi

# ---------------------------------------------------------------
# Step 2: Get chat ID
# ---------------------------------------------------------------
echo ""
echo -e "${YELLOW}STEP 2 — Get your Chat ID${NC}"
echo ""
echo "  1. Go to Telegram and send ANY message to your new bot"
echo "     (search for it by the username you just created)"
echo "  2. We'll fetch your chat ID automatically..."
echo ""

sleep 2

RESPONSE=$(curl -s "https://api.telegram.org/bot${BOT_TOKEN}/getUpdates")

# Try to extract chat ID
CHAT_ID=$(echo "$RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    updates = data.get('result', [])
    if updates:
        cid = updates[-1]['message']['chat']['id']
        print(cid)
    else:
        print('')
except:
    print('')
" 2>/dev/null)

if [ -z "$CHAT_ID" ]; then
    echo "  Could not auto-detect chat ID."
    echo "  Go to: https://api.telegram.org/bot${BOT_TOKEN}/getUpdates"
    echo "  Find the 'id' field under 'chat' in the response"
    echo ""
    read -p "  Paste your chat ID: " CHAT_ID
fi

if [ -z "$CHAT_ID" ]; then
    echo "No chat ID. Exiting."
    exit 1
fi

echo ""
echo "  Chat ID detected: $CHAT_ID"

# ---------------------------------------------------------------
# Step 3: Test the connection
# ---------------------------------------------------------------
echo ""
echo -e "${YELLOW}STEP 3 — Testing connection${NC}"

TEST_RESPONSE=$(curl -s -X POST \
    "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
    -d "chat_id=${CHAT_ID}" \
    -d "text=🤖 PropBot connected! You will receive trade alerts here." \
    -d "parse_mode=Markdown")

OK=$(echo "$TEST_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('ok',''))" 2>/dev/null)

if [ "$OK" = "True" ]; then
    echo -e "  ${GREEN}✓ Test message sent — check your Telegram!${NC}"
else
    echo "  Warning: Test message may have failed. Response:"
    echo "  $TEST_RESPONSE"
fi

# ---------------------------------------------------------------
# Step 4: Save to .env
# ---------------------------------------------------------------
echo ""
echo -e "${YELLOW}STEP 4 — Saving to .env${NC}"

REPO_DIR="$HOME/PropBot"
ENV_FILE="$REPO_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "  .env not found at $ENV_FILE"
    echo "  Run setup_mac.sh first, then re-run this script."
    exit 1
fi

# Update or add TELEGRAM_TOKEN
if grep -q "TELEGRAM_TOKEN=" "$ENV_FILE"; then
    sed -i '' "s/TELEGRAM_TOKEN=.*/TELEGRAM_TOKEN=${BOT_TOKEN}/" "$ENV_FILE"
else
    echo "TELEGRAM_TOKEN=${BOT_TOKEN}" >> "$ENV_FILE"
fi

# Update or add TELEGRAM_CHAT_ID
if grep -q "TELEGRAM_CHAT_ID=" "$ENV_FILE"; then
    sed -i '' "s/TELEGRAM_CHAT_ID=.*/TELEGRAM_CHAT_ID=${CHAT_ID}/" "$ENV_FILE"
else
    echo "TELEGRAM_CHAT_ID=${CHAT_ID}" >> "$ENV_FILE"
fi

echo -e "  ${GREEN}✓ Credentials saved to $ENV_FILE${NC}"

# ---------------------------------------------------------------
# Done
# ---------------------------------------------------------------
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Telegram alerts are ready!              ║${NC}"
echo -e "${GREEN}║                                          ║${NC}"
echo -e "${GREEN}║  You'll receive alerts for:              ║${NC}"
echo -e "${GREEN}║   • Every trade entry                    ║${NC}"
echo -e "${GREEN}║   • Every trade exit (with P&L)          ║${NC}"
echo -e "${GREEN}║   • Daily profit target hit              ║${NC}"
echo -e "${GREEN}║   • Daily loss limit hit                 ║${NC}"
echo -e "${GREEN}║   • End of day summary                   ║${NC}"
echo -e "${GREEN}║   • Any errors                           ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""
