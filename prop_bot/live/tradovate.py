"""
Tradovate REST API wrapper.
Docs: https://api.tradovate.com/

Authentication uses OAuth2 password flow.
Always use demo=True until strategy is validated live.

Supported operations:
  - authenticate()
  - get_account()
  - place_order(symbol, action, qty, order_type, price, stop_price)
  - cancel_order(order_id)
  - get_positions()
  - get_open_orders()
  - liquidate_position(account_id, symbol)
"""

import logging
import time
from typing import Optional, Dict, Any
import requests

logger = logging.getLogger(__name__)

DEMO_URL = "https://demo.tradovateapi.com/v1"
LIVE_URL = "https://live.tradovateapi.com/v1"


class TradovateClient:
    def __init__(self, config):
        self.cfg = config.live
        self.base_url = DEMO_URL if self.cfg.tradovate_demo else LIVE_URL
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0
        self._account_id: Optional[int] = None

        mode = "DEMO" if self.cfg.tradovate_demo else "LIVE"
        logger.info("TradovateClient initialised [%s]", mode)
        if not self.cfg.tradovate_demo:
            logger.warning(
                "⚠ LIVE TRADING MODE ACTIVE — ensure strategy is fully validated"
            )

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def authenticate(self) -> bool:
        """OAuth2 password grant. Token valid ~24h."""
        if not all([self.cfg.tradovate_cid, self.cfg.tradovate_secret,
                    self.cfg.tradovate_username, self.cfg.tradovate_password]):
            raise ValueError(
                "Missing Tradovate credentials. Set env vars: "
                "TRADOVATE_CID, TRADOVATE_SECRET, TRADOVATE_USERNAME, TRADOVATE_PASSWORD"
            )
        resp = self._post("/auth/oauthtoken", {
            "name": self.cfg.tradovate_username,
            "password": self.cfg.tradovate_password,
            "appId": "PropBot",
            "appVersion": "1.0",
            "cid": int(self.cfg.tradovate_cid),
            "sec": self.cfg.tradovate_secret,
        })
        if "accessToken" not in resp:
            raise RuntimeError(f"Auth failed: {resp}")
        self._token = resp["accessToken"]
        self._token_expiry = time.time() + resp.get("expirationTime", 86400)
        logger.info("Tradovate authenticated successfully")
        return True

    def _ensure_auth(self):
        if not self._token or time.time() > self._token_expiry - 300:
            self.authenticate()

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    def get_account(self) -> Dict[str, Any]:
        self._ensure_auth()
        accounts = self._get("/account/list")
        if not accounts:
            raise RuntimeError("No accounts found")
        acct = accounts[0]
        self._account_id = acct["id"]
        return acct

    def get_cash_balance(self) -> float:
        """Return current account cash balance."""
        self._ensure_auth()
        resp = self._get(f"/cashBalance/getcashbalancesnapshot?accountId={self._account_id}")
        return float(resp.get("totalCashValue", 0))

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def place_market_order(self, symbol: str, action: str, qty: int) -> dict:
        """
        action: 'Buy' or 'Sell'
        Returns order response dict.
        """
        self._ensure_auth()
        if not self._account_id:
            self.get_account()

        logger.info("MARKET ORDER: %s %d %s", action, qty, symbol)
        return self._post("/order/placeorder", {
            "accountSpec": str(self._account_id),
            "accountId": self._account_id,
            "action": action,
            "symbol": symbol,
            "orderQty": qty,
            "orderType": "Market",
            "timeInForce": "FOK",
            "isAutomated": True,
        })

    def place_stop_order(
        self, symbol: str, action: str, qty: int, stop_price: float
    ) -> dict:
        self._ensure_auth()
        logger.info("STOP ORDER: %s %d %s @ %.4f", action, qty, symbol, stop_price)
        return self._post("/order/placeorder", {
            "accountId": self._account_id,
            "action": action,
            "symbol": symbol,
            "orderQty": qty,
            "orderType": "Stop",
            "stopPrice": stop_price,
            "timeInForce": "GTC",
            "isAutomated": True,
        })

    def place_bracket_order(
        self, symbol: str, action: str, qty: int,
        stop_price: float, target_price: Optional[float] = None,
    ) -> dict:
        """Entry market order with attached stop loss (and optional target)."""
        entry = self.place_market_order(symbol, action, qty)
        exit_action = "Sell" if action == "Buy" else "Buy"

        self.place_stop_order(symbol, exit_action, qty, stop_price)

        if target_price:
            self._post("/order/placeorder", {
                "accountId": self._account_id,
                "action": exit_action,
                "symbol": symbol,
                "orderQty": qty,
                "orderType": "Limit",
                "price": target_price,
                "timeInForce": "GTC",
                "isAutomated": True,
            })
        return entry

    def cancel_all_orders(self) -> list:
        self._ensure_auth()
        orders = self._get(f"/order/list?accountId={self._account_id}")
        cancelled = []
        for o in orders:
            if o.get("ordStatus") in ("Working", "PendingNew"):
                self._post(f"/order/cancelorder", {"orderId": o["id"]})
                cancelled.append(o["id"])
        return cancelled

    def liquidate_position(self, symbol: str) -> dict:
        """Send flatten-all for a symbol (Tradovate 'liquidatePosition' endpoint)."""
        self._ensure_auth()
        return self._post("/order/liquidateposition", {
            "accountId": self._account_id,
            "contractId": self._symbol_to_contract_id(symbol),
            "admin": False,
        })

    # ------------------------------------------------------------------
    # Position / fills
    # ------------------------------------------------------------------

    def get_positions(self) -> list:
        self._ensure_auth()
        return self._get(f"/position/list?accountId={self._account_id}")

    def get_fills(self, since_timestamp: Optional[str] = None) -> list:
        self._ensure_auth()
        url = f"/fill/list?accountId={self._account_id}"
        if since_timestamp:
            url += f"&timestamp={since_timestamp}"
        return self._get(url)

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def _get(self, path: str) -> Any:
        r = requests.get(self.base_url + path, headers=self._headers(), timeout=15)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: dict) -> Any:
        r = requests.post(self.base_url + path, json=body,
                          headers=self._headers(), timeout=15)
        r.raise_for_status()
        return r.json()

    def _symbol_to_contract_id(self, symbol: str) -> int:
        contracts = self._get(f"/contract/find?name={symbol}")
        if not contracts:
            raise ValueError(f"Contract not found: {symbol}")
        return contracts[0]["id"] if isinstance(contracts, list) else contracts["id"]
