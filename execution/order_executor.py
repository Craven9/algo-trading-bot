"""
execution/order_executor.py — Alpaca paper trading order management
Places, modifies, and cancels orders. Supports dry run mode (no real orders).
"""

import logging
from datetime import datetime
from typing import Optional
import aiohttp

log = logging.getLogger(__name__)


class OrderExecutor:
    def __init__(self, settings: dict):
        self.settings = settings
        self.cfg = settings["execution"]
        self.mode = settings["mode"]
        self.dry_run = self.mode["dry_run"]
        self.paper = self.mode["paper_trading"]

        base_url = self.cfg.get("alpaca_base_url", "https://paper-api.alpaca.markets")
        self.base_url = base_url
        self.api_key = self.cfg.get("alpaca_api_key", "")
        self.secret_key = self.cfg.get("alpaca_secret_key", "")

        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers={
                "APCA-API-KEY-ID": self.api_key,
                "APCA-API-SECRET-KEY": self.secret_key,
                "Content-Type": "application/json",
            })
        return self._session

    async def _post(self, path: str, body: dict) -> Optional[dict]:
        if self.dry_run:
            log.info(f"[DRY RUN] POST {path} | {body}")
            return self._mock_order(body)
        try:
            session = await self._get_session()
            async with session.post(f"{self.base_url}{path}", json=body, timeout=aiohttp.ClientTimeout(total=10)) as r:
                data = await r.json()
                if r.status not in (200, 201):
                    log.error(f"Alpaca error {r.status}: {data}")
                    return None
                return data
        except Exception as exc:
            log.exception(f"Order executor error: {exc}")
            return None

    async def _delete(self, path: str) -> bool:
        if self.dry_run:
            log.info(f"[DRY RUN] DELETE {path}")
            return True
        try:
            session = await self._get_session()
            async with session.delete(f"{self.base_url}{path}", timeout=aiohttp.ClientTimeout(total=10)) as r:
                return r.status in (200, 204)
        except Exception as exc:
            log.exception(f"Cancel order error: {exc}")
            return False

    async def place_entry(
        self,
        ticker: str,
        shares: int,
        entry_price: float,
        stop_price: float,
        targets: list[float],
    ) -> Optional[dict]:
        """Place a bracket order: entry limit + stop loss."""
        order_type = self.cfg.get("order_type", "limit")
        offset_pct = self.cfg.get("limit_offset_pct", 0.1) / 100
        limit_price = round(entry_price * (1 + offset_pct), 2)

        body = {
            "symbol": ticker,
            "qty": str(shares),
            "side": "buy",
            "type": order_type,
            "time_in_force": "day",
            "limit_price": str(limit_price) if order_type == "limit" else None,
            "order_class": "bracket",
            "stop_loss": {"stop_price": str(round(stop_price, 2))},
        }
        # Remove None values
        body = {k: v for k, v in body.items() if v is not None}

        log.info(f"Placing entry: {ticker} {shares} shares @ ${limit_price:.2f} | stop=${stop_price:.2f}")
        result = await self._post("/v2/orders", body)

        if result:
            log.info(f"Order placed: {ticker} | id={result.get('id')} | status={result.get('status')}")
        return result

    async def close_position(self, ticker: str, reason: str = "manual") -> bool:
        """Market sell all shares in a position."""
        log.info(f"Closing position: {ticker} | reason={reason}")
        if self.dry_run:
            log.info(f"[DRY RUN] Close {ticker}")
            return True
        result = await self._post("/v2/orders", {
            "symbol": ticker,
            "qty": None,  # use liquidate endpoint instead
            "side": "sell",
            "type": "market",
            "time_in_force": "day",
        })
        # Prefer the liquidate endpoint
        try:
            session = await self._get_session()
            async with session.delete(f"{self.base_url}/v2/positions/{ticker}", timeout=aiohttp.ClientTimeout(total=10)) as r:
                return r.status in (200, 204)
        except Exception:
            return bool(result)

    async def close_partial(self, ticker: str, shares: int, reason: str = "") -> Optional[dict]:
        """Sell a specific number of shares (partial exit)."""
        log.info(f"Partial exit: {ticker} {shares} shares | {reason}")
        body = {
            "symbol": ticker,
            "qty": str(shares),
            "side": "sell",
            "type": "market",
            "time_in_force": "day",
        }
        return await self._post("/v2/orders", body)

    async def update_stop(self, order_id: str, new_stop: float) -> bool:
        """Patch the stop loss on an existing bracket order."""
        if self.dry_run:
            log.info(f"[DRY RUN] Update stop {order_id} → ${new_stop:.2f}")
            return True
        result = await self._post(f"/v2/orders/{order_id}", {"stop_price": str(round(new_stop, 2))})
        return result is not None

    async def get_account(self) -> Optional[dict]:
        """Fetch Alpaca account info (equity, buying power)."""
        if self.dry_run:
            return {"equity": "100000", "buying_power": "100000", "portfolio_value": "100000"}
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/v2/account", timeout=aiohttp.ClientTimeout(total=10)) as r:
                return await r.json() if r.status == 200 else None
        except Exception as exc:
            log.exception(f"Get account error: {exc}")
            return None

    def _mock_order(self, body: dict) -> dict:
        """Return a fake order dict for dry run mode."""
        import uuid
        return {
            "id": str(uuid.uuid4()),
            "status": "filled",
            "symbol": body.get("symbol", ""),
            "qty": body.get("qty", "0"),
            "filled_qty": body.get("qty", "0"),
            "filled_avg_price": body.get("limit_price", "0"),
            "side": body.get("side", "buy"),
            "type": body.get("type", "limit"),
            "created_at": datetime.now().isoformat(),
            "_dry_run": True,
        }

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
