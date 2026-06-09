#!/bin/bash
# Backtest NQ — runs both strategies and saves all results
cd "$(dirname "$0")"
source venv/bin/activate

echo ""
echo "━━━ NQ Dual Thrust (daily bars, 2015-2025) ━━━"
python prop_bot/main_backtest.py \
  --instrument NQ \
  --strategy dual_thrust \
  --start 2015-01-01 --end 2025-01-01 \
  --prop apex_50k \
  --monte-carlo --plot

echo ""
echo "━━━ NQ IBS Mean Reversion (daily bars, 2015-2025) ━━━"
python prop_bot/main_backtest.py \
  --instrument NQ \
  --strategy ibs \
  --start 2015-01-01 --end 2025-01-01 \
  --prop apex_50k \
  --monte-carlo --plot

echo ""
echo "Results saved to: $(pwd)/prop_bot/results/"
echo "Run this to open charts: bash view_results.sh"
