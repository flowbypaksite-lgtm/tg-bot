"""Binance auto payment detection (read-only API key).

The user pays to the shop's Binance Pay ID / USDT wallet and then submits the
Order ID (Binance Pay transaction/order id) or the on-chain TxID.  The bot
signs a request with the shop's read-only API key and looks for a matching
incoming payment using three signals:

    1. Order ID / Transaction ID (exact, case-insensitive)
    2. Amount   (must match the expected amount within a small tolerance)
    3. Time     (payment must be inside the configured time window)

Endpoints used (both need only the "Enable Reading" permission):

    GET /sapi/v1/pay/transactions        -> Binance Pay history
    GET /sapi/v1/capital/deposit/hisrec  -> USDT TRC20/BEP20 deposit history

Nothing here can move funds: the key is read-only and no order/withdraw
endpoint is ever called.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import aiohttp

logger = logging.getLogger(__name__)

BASE_URL = "https://api.binance.com"
STABLES = {"USDT", "BUSD", "USDC", "FDUSD"}


@dataclass
class BinanceMatch:
    ok: bool
    reason: str = ""
    order_id: str = ""
    amount: float = 0.0
    currency: str = ""
    timestamp: int = 0
    source: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


def _sign(secret: str, query: str) -> str:
    return hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()


async def _signed_get(
    api_key: str,
    api_secret: str,
    path: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 20,
) -> Any:
    params = dict(params or {})
    params["timestamp"] = int(time.time() * 1000)
    params["recvWindow"] = 60000
    query = urlencode(params)
    url = f"{BASE_URL}{path}?{query}&signature={_sign(api_secret, query)}"
    headers = {"X-MBX-APIKEY": api_key}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
        async with session.get(url, headers=headers) as resp:
            body = await resp.text()
            if resp.status != 200:
                raise RuntimeError(f"Binance {path} failed [{resp.status}]: {body[:300]}")
            import json

            return json.loads(body)


async def fetch_pay_transactions(
    api_key: str, api_secret: str, start_ms: int, end_ms: int
) -> List[Dict[str, Any]]:
    try:
        data = await _signed_get(
            api_key,
            api_secret,
            "/sapi/v1/pay/transactions",
            {"startTime": start_ms, "endTime": end_ms, "limit": 100},
        )
    except Exception as exc:
        logger.warning(f"Binance Pay history unavailable: {exc}")
        return []
    if isinstance(data, dict):
        return data.get("data") or []
    return []


async def fetch_deposit_history(
    api_key: str, api_secret: str, start_ms: int, end_ms: int
) -> List[Dict[str, Any]]:
    try:
        data = await _signed_get(
            api_key,
            api_secret,
            "/sapi/v1/capital/deposit/hisrec",
            {"startTime": start_ms, "endTime": end_ms, "status": 1},
        )
    except Exception as exc:
        logger.warning(f"Binance deposit history unavailable: {exc}")
        return []
    return data if isinstance(data, list) else []


def _ids_of(record: Dict[str, Any]) -> List[str]:
    keys = ("orderId", "transactionId", "txId", "tranId", "id", "orderNo")
    out = []
    for key in keys:
        val = record.get(key)
        if val not in (None, ""):
            out.append(str(val).strip().lower())
    return out


def _normalise_pay(record: Dict[str, Any]) -> Dict[str, Any]:
    amount = float(record.get("amount") or 0)
    return {
        "ids": _ids_of(record),
        "amount": abs(amount),
        "incoming": amount > 0,
        "currency": (record.get("currency") or "").upper(),
        "time": int(record.get("transactionTime") or 0),
        "source": "binance_pay",
        "raw": record,
    }


def _normalise_deposit(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ids": _ids_of(record),
        "amount": float(record.get("amount") or 0),
        "incoming": True,
        "currency": (record.get("coin") or "").upper(),
        "time": int(record.get("insertTime") or 0),
        "source": f"deposit_{(record.get('network') or '').lower() or 'onchain'}",
        "raw": record,
    }


async def verify_payment(
    api_key: str,
    api_secret: str,
    submitted_id: str,
    expected_amount: float,
    window_hours: int = 24,
    tolerance: float = 0.02,
    used_ids: Optional[set] = None,
    allow_amount_only: bool = False,
) -> BinanceMatch:
    """Look for an incoming payment matching id + amount + time."""
    if not api_key or not api_secret:
        return BinanceMatch(False, "not_configured")

    submitted = (submitted_id or "").strip().lower()
    used_ids = {str(x).lower() for x in (used_ids or set())}

    end_ms = int(time.time() * 1000)
    start_ms = end_ms - window_hours * 3600 * 1000

    records: List[Dict[str, Any]] = []
    for raw in await fetch_pay_transactions(api_key, api_secret, start_ms, end_ms):
        records.append(_normalise_pay(raw))
    for raw in await fetch_deposit_history(api_key, api_secret, start_ms, end_ms):
        records.append(_normalise_deposit(raw))

    if not records:
        return BinanceMatch(False, "no_transactions")

    amount_ok = lambda amt: abs(amt - expected_amount) <= max(tolerance, expected_amount * 0.01)

    id_hit = None
    for rec in records:
        if submitted and submitted in rec["ids"]:
            id_hit = rec
            break

    if id_hit:
        if any(i in used_ids for i in id_hit["ids"]):
            return BinanceMatch(False, "already_used", order_id=submitted)
        if not id_hit["incoming"]:
            return BinanceMatch(False, "outgoing", order_id=submitted)
        if id_hit["currency"] and id_hit["currency"] not in STABLES:
            return BinanceMatch(False, "wrong_currency", order_id=submitted,
                                currency=id_hit["currency"])
        if not amount_ok(id_hit["amount"]):
            return BinanceMatch(False, "amount_mismatch", order_id=submitted,
                                amount=id_hit["amount"], currency=id_hit["currency"])
        if id_hit["time"] and not (start_ms <= id_hit["time"] <= end_ms + 60000):
            return BinanceMatch(False, "too_old", order_id=submitted, amount=id_hit["amount"])
        return BinanceMatch(
            True, "matched", order_id=(id_hit["ids"][0] if id_hit["ids"] else submitted),
            amount=id_hit["amount"], currency=id_hit["currency"],
            timestamp=id_hit["time"], source=id_hit["source"], raw=id_hit["raw"],
        )

    if allow_amount_only:
        for rec in records:
            if (
                rec["incoming"]
                and amount_ok(rec["amount"])
                and not any(i in used_ids for i in rec["ids"])
                and (not rec["currency"] or rec["currency"] in STABLES)
            ):
                return BinanceMatch(
                    True, "matched_amount", order_id=(rec["ids"][0] if rec["ids"] else submitted),
                    amount=rec["amount"], currency=rec["currency"],
                    timestamp=rec["time"], source=rec["source"], raw=rec["raw"],
                )

    return BinanceMatch(False, "not_found", order_id=submitted)


async def test_credentials(api_key: str, api_secret: str) -> Dict[str, Any]:
    """Ping the account endpoint so the admin can validate the API key."""
    if not api_key or not api_secret:
        return {"ok": False, "error": "API key / secret not configured."}
    try:
        data = await _signed_get(api_key, api_secret, "/sapi/v1/account/status")
        return {"ok": True, "data": data}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}
