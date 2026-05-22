"""
Telegram alert system for live trading events.

Setup:
  1. Message @BotFather on Telegram, create a bot, get TOKEN
  2. Message your bot once, then run:
     curl "https://api.telegram.org/bot<TOKEN>/getUpdates"
     to find your CHAT_ID
  3. Set env vars: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
"""

import logging
import time
from typing import Optional
import requests

logger = logging.getLogger(__name__)

_TELEGRAM_URL = "https://api.telegram.org/bot{token}/sendMessage"


class AlertManager:
    def __init__(self, config):
        self.cfg = config.alerts
        self.enabled = bool(self.cfg.telegram_token and self.cfg.telegram_chat_id)
        if not self.enabled:
            logger.info("Telegram alerts disabled (no token/chat_id in env)")

    def send(self, message: str, level: str = "INFO") -> bool:
        if not self.enabled:
            logger.info("[ALERT] %s", message)
            return True

        emoji = {"INFO": "ℹ️", "TRADE": "📈", "WARN": "⚠️", "ERROR": "🚨", "HALT": "🛑"}.get(level, "")
        full_msg = f"{emoji} *PropBot* [{level}]\n{message}"

        try:
            resp = requests.post(
                _TELEGRAM_URL.format(token=self.cfg.telegram_token),
                json={
                    "chat_id": self.cfg.telegram_chat_id,
                    "text": full_msg,
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error("Telegram send failed: %s", e)
            return False

    def trade_entry(self, instrument: str, direction: str, price: float,
                    contracts: int, stop: float):
        if not self.cfg.alert_on_entry:
            return
        msg = (
            f"*ENTRY* {direction.upper()} {contracts}x {instrument}\n"
            f"Price: `{price:.4f}`\n"
            f"Stop:  `{stop:.4f}`\n"
            f"Risk:  `${abs(price - stop) * contracts:.2f}`"
        )
        self.send(msg, "TRADE")

    def trade_exit(self, instrument: str, direction: str, entry: float,
                   exit_price: float, pnl_net: float, reason: str):
        if not self.cfg.alert_on_exit:
            return
        sign = "+" if pnl_net >= 0 else ""
        emoji = "✅" if pnl_net > 0 else "❌"
        msg = (
            f"{emoji} *EXIT* {direction.upper()} {instrument}\n"
            f"Entry → Exit: `{entry:.4f}` → `{exit_price:.4f}`\n"
            f"Net P&L: `{sign}${pnl_net:.2f}`\n"
            f"Reason: {reason}"
        )
        self.send(msg, "TRADE")

    def daily_halt(self, reason: str, daily_pnl: float, equity: float):
        if not self.cfg.alert_on_daily_loss_limit:
            return
        msg = (
            f"*TRADING HALTED*\n"
            f"Reason: {reason}\n"
            f"Daily P&L: `${daily_pnl:.2f}`\n"
            f"Equity: `${equity:.2f}`"
        )
        self.send(msg, "HALT")

    def daily_summary(self, date: str, daily_pnl: float, trades: int,
                      equity: float, dd_remaining: float):
        msg = (
            f"*Daily Summary* {date}\n"
            f"P&L:      `${daily_pnl:+.2f}`\n"
            f"Trades:   `{trades}`\n"
            f"Equity:   `${equity:.2f}`\n"
            f"DD avail: `${dd_remaining:.2f}`"
        )
        self.send(msg, "INFO")

    def error(self, message: str):
        if not self.cfg.alert_on_error:
            return
        self.send(f"Error: {message}", "ERROR")
