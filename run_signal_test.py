"""
run_signal_test.py
End-to-end signal-pipeline + Telegram alert smoke test.
Run with:  python run_signal_test.py
"""
import sys
import os
import json
import numpy as np
import pandas as pd
from datetime import datetime, timezone

sys.path.insert(0, ".")

RESET  = "\033[0m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
BOLD   = "\033[1m"

def ok(msg):   print(f"  {GREEN}OK  {msg}{RESET}")
def warn(msg): print(f"  {YELLOW}WARN {msg}{RESET}")
def fail(msg): print(f"  {RED}FAIL {msg}{RESET}")

# ── Synthetic AR(1) OHLCV (200 business days, seed=42) ─────────────────────
rng    = np.random.default_rng(42)
n      = 200
prices = [100.0]
for _ in range(n - 1):
    prices.append(prices[-1] * 0.99 + 100.0 * 0.01 + rng.normal(0, 0.5))
prices = np.array(prices)
noise  = rng.uniform(0, 0.5, n)
idx    = pd.date_range("2024-01-03", periods=n, freq="B", tz="UTC")
ohlcv  = pd.DataFrame(
    {
        "open":   prices + rng.uniform(-0.3, 0.3, n),
        "high":   prices + noise,
        "low":    prices - noise,
        "close":  prices,
        "volume": rng.integers(1000, 10000, n).astype(float),
    },
    index=idx,
)

print()
print(f"{BOLD}╔═══════════════════════════════════════════════╗{RESET}")
print(f"{BOLD}║   Quant-PF-Signals-Bot  ·  Signal Test       ║{RESET}")
print(f"{BOLD}╚═══════════════════════════════════════════════╝{RESET}")

passed = 0
failed = 0

# ─────────────────────────────────────────────────────────────────────────────
# TEST 1: Indicators
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{BOLD}[1/4] Indicators{RESET}")
try:
    from signals.indicators.bollinger import compute_bollinger
    from signals.indicators.zscore    import compute_zscore
    from signals.indicators.atr       import compute_atr

    bb  = compute_bollinger(ohlcv["close"], period=20, n_std=2.0)
    zs  = compute_zscore(ohlcv["close"], window=20)
    atr = compute_atr(ohlcv)

    assert not bb.empty and "upper" in bb.columns
    assert not zs.empty
    atr_val = float(atr.dropna().iloc[-1])
    assert atr_val > 0

    ok(f"Bollinger Bands  ({len(bb)} rows, last pct_b={bb['pct_b'].iloc[-1]:.4f})")
    ok(f"Z-Score          (last={float(zs.iloc[-1]):.4f})")
    ok(f"ATR-14           (last={atr_val:.4f})")
    passed += 3
except Exception as e:
    fail(f"Indicators failed: {e}")
    failed += 1
    atr_val = 0.5   # fallback for later steps

# ─────────────────────────────────────────────────────────────────────────────
# TEST 2: Strategy signal generation
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{BOLD}[2/4] Strategy Signal Generation{RESET}")
LABELS = {1: "LONG", -1: "SHORT", 0: "FLAT"}
results = {}

try:
    from signals.strategy.bb_reversion     import BollingerReversion
    from signals.strategy.zscore_reversion import ZScoreReversion

    cfg_bb = {
        "bollinger": {"period": 20, "std_dev": 2.0, "exit_band": 0.5, "squeeze_filter": False}
    }
    cfg_zs = {
        "zscore": {"lookback_period": 20, "entry_threshold": 2.0, "exit_threshold": 0.5}
    }

    for name, strat_cls, cfg in [
        ("BollingerReversion", BollingerReversion, cfg_bb),
        ("ZScoreReversion",    ZScoreReversion,    cfg_zs),
    ]:
        strat = strat_cls(cfg, instrument="GC")
        res   = strat.generate_signals(ohlcv)
        assert "signal" in res.columns, f"Missing signal column in {name}"
        sig  = int(res["signal"].iloc[-1])
        stre = float(res["signal_strength"].iloc[-1]) if "signal_strength" in res.columns else float("nan")
        results[name] = {"signal": sig, "strength": stre}
        emoji = {"LONG": "up", "SHORT": "dn", "FLAT": "--"}[LABELS[sig]]
        ok(f"{name}: [{emoji}] {LABELS[sig]}  (strength={stre:.4f})")
        passed += 1
except Exception as e:
    fail(f"Strategy generation failed: {e}")
    failed += 1

# ─────────────────────────────────────────────────────────────────────────────
# TEST 3: Position Sizer
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{BOLD}[3/4] Position Sizer{RESET}")
try:
    from signals.risk.position_sizer import PositionSizer

    cases = [
        ("fixed",         {"sizing_method": "fixed",       "fixed": {"contracts": 2},
                           "limits": {"max_position_contracts": 5}}),
        ("fractional",    {"sizing_method": "fractional",  "fractional":
                           {"account_size": 100000, "risk_per_trade_pct": 0.01,
                            "atr_period": 14, "atr_multiplier": 2.0},
                           "limits": {"max_position_contracts": 5}}),
        ("vol_target",    {"sizing_method": "volatility_target", "volatility_target":
                           {"account_size": 100000, "daily_vol_target_pct": 0.005,
                            "vol_lookback": 20},
                           "limits": {"max_position_contracts": 5}}),
    ]
    for label, cfg in cases:
        sizer = PositionSizer({"risk": cfg})
        c = sizer.size(ohlcv, point_value=100.0)
        assert c >= 0, f"Negative contract count for {label}"
        ok(f"PositionSizer [{label}] -> {c} contract(s)")
        passed += 1
except Exception as e:
    fail(f"Position sizer failed: {e}")
    failed += 1

# ─────────────────────────────────────────────────────────────────────────────
# TEST 4: Telegram Alert Module
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{BOLD}[4/4] Telegram Alert Module{RESET}")
try:
    token   = os.getenv("TELEGRAM_TOKEN",   "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    from prop_bot.config import BotConfig
    from prop_bot.utils.alerts import AlertManager

    cfg_bot = BotConfig()
    am      = AlertManager(cfg_bot)

    if not token or not chat_id:
        warn("TELEGRAM_TOKEN / TELEGRAM_CHAT_ID not in environment.")
        warn("Add them to a .env file to enable live Telegram sends.")
        result = am.send("dry-run test", level="INFO")
        assert result is True, "send() must return True in no-creds mode"
        ok("AlertManager (disabled mode): returns True, no crash")
        passed += 1
    else:
        bb_sig = results.get("BollingerReversion", {}).get("signal", 0)
        bb_str = results.get("BollingerReversion", {}).get("strength", 0.0)
        msg = (
            "Test Signal Update\n"
            f"Time:     {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"Strategy: BollingerReversion (GC)\n"
            f"Signal:   {bb_sig} ({LABELS.get(bb_sig, '?')})\n"
            f"Strength: {bb_str:.4f}\n"
            f"ATR-14:   {atr_val:.4f}\n"
            "(Automated test)"
        )
        sent = am.send(msg, "INFO")
        if sent:
            ok("Telegram message SENT — check your chat!")
            passed += 1
        else:
            fail("Telegram send FAILED — check token/chat_id and network access")
            failed += 1
except Exception as e:
    fail(f"Telegram module error: {e}")
    failed += 1

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
bb_sig = results.get("BollingerReversion", {}).get("signal", "N/A")
zs_sig = results.get("ZScoreReversion",    {}).get("signal", "N/A")

print()
print(f"{BOLD}  +------------------------------------------------+{RESET}")
print(f"{BOLD}  |   SIGNAL SNAPSHOT  (synthetic 200-bar data)   |{RESET}")
print(f"{BOLD}  +-------------------+----------------------------+{RESET}")

bb_lbl = LABELS.get(bb_sig, str(bb_sig))
zs_lbl = LABELS.get(zs_sig, str(zs_sig))
print(f"{BOLD}  | BollingerReversion| {bb_lbl:<27}|{RESET}")
print(f"{BOLD}  | ZScoreReversion   | {zs_lbl:<27}|{RESET}")
print(f"{BOLD}  +-------------------+----------------------------+{RESET}")
print()
color = GREEN if failed == 0 else RED
print(f"  {color}{BOLD}{passed} checks passed, {failed} failed.{RESET}")
print()

sys.exit(0 if failed == 0 else 1)
