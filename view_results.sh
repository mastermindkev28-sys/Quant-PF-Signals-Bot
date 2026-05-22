#!/bin/bash
# Open all backtest result charts in Preview
RESULTS_DIR="$HOME/PropBot/prop_bot/results"

if [ ! -d "$RESULTS_DIR" ]; then
    echo "No results yet — run a backtest first"
    echo "  bash ~/PropBot/backtest_nq.sh"
    exit 1
fi

PNG_COUNT=$(find "$RESULTS_DIR" -name "*.png" 2>/dev/null | wc -l | tr -d ' ')

if [ "$PNG_COUNT" -eq 0 ]; then
    echo "No charts found. Run with --plot flag:"
    echo "  bash ~/PropBot/backtest_nq.sh"
    exit 1
fi

echo "Opening $PNG_COUNT chart(s)..."
open "$RESULTS_DIR"/*.png 2>/dev/null || echo "Charts are in: $RESULTS_DIR"
