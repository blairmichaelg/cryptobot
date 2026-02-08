"""Wallet daemon interface for local crypto wallet RPC and public APIs.

Provides an async context-managed client that keeps an HTTP session for
JSON-RPC calls to the local wallet daemon and read-only public API calls
(mempool fee lookups, on-chain balance queries, etc.).
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)


class WalletDaemon:
    """Interface for local crypto wallet daemons (Electrum, Core).

    Uses JSON-RPC to manage keys and sign transactions headless.
    """

    def __init__(
        self,
        rpc_urls: Dict[str, str],
        rpc_user: str,
        rpc_pass: str,
    ) -> None:
        """Initialize the WalletDaemon.

        Args:
            rpc_urls: Mapping of coin symbols to their RPC URLs
                (e.g. {'BTC': 'http://...', 'LTC': '...'}).
            rpc_user: The username for RPC authentication.
            rpc_pass: The password for RPC authentication.
        """
        self.urls = rpc_urls
        self.auth = (
            aiohttp.BasicAuth(rpc_user, rpc_pass)
            if rpc_user else None
        )
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Return the shared aiohttp session, creating one if needed."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(auth=self.auth)
        return self._session

    async def _rpc_call(
        self,
        coin: str,
        method: str,
        params: Optional[list] = None,
    ) -> Any:
        """Execute a JSON-RPC call to a coin wallet daemon.

        Args:
            coin: Cryptocurrency symbol (e.g. 'BTC').
            method: RPC method name to invoke.
            params: Optional list of positional parameters.

        Returns:
            The 'result' field from the JSON-RPC response,
            or None on error.
        """
        if params is None:
            params = []
        url = self.urls.get(coin.upper())
        if not url:
            logger.error(
                "No RPC URL configured for coin: %s", coin
            )
            return None

        payload = {
            "jsonrpc": "2.0",
            "id": f"crypto-bot-{coin}",
            "method": method,
            "params": params,
        }

        try:
            session = await self._get_session()
            async with session.post(
                url, json=payload
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("error"):
                        logger.error(
                            "RPC Error %s:%s: %s",
                            coin, method, data["error"],
                        )
                        return None
                    return data.get("result")
                logger.error(
                    "RPC HTTP Error %s on %s",
                    response.status, coin,
                )
                return None
        except Exception as e:
            logger.error(
                "Wallet Daemon Connection Failed (%s): %s",
                coin, e,
            )
            return None

    async def get_balance(
        self, coin: str = "BTC"
    ) -> Optional[Dict[str, Any]]:
        """Get confirmed and unconfirmed balance for a coin.

        Args:
            coin: Cryptocurrency symbol (default 'BTC').

        Returns:
            Balance information dict, or None on error.
        """
        return await self._rpc_call(coin, "getbalance")

    async def __aenter__(self) -> "WalletDaemon":
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> bool:
        """Async context manager exit with cleanup."""
        await self.close()
        return False

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def get_unused_address(
        self, coin: str = "BTC"
    ) -> Optional[str]:
        """Generate a new receiving address.

        Args:
            coin: Cryptocurrency symbol (default 'BTC').

        Returns:
            A new unused address string, or None on error.
        """
        return await self._rpc_call(coin, "getunusedaddress")

    async def validate_address(
        self, address: str, coin: str = "BTC"
    ) -> bool:
        """Check if an address is valid on the network.

        Args:
            address: The wallet address to validate.
            coin: Cryptocurrency symbol (default 'BTC').

        Returns:
            True if the address is valid, False otherwise.
        """
        res = await self._rpc_call(
            coin, "validateaddress", [address]
        )
        if res is None:
            return False
        if isinstance(res, bool):
            return res
        return res.get("isvalid", False)

    async def check_connection(
        self, coin: str = "BTC"
    ) -> bool:
        """Health check for the wallet daemon connectivity.

        Args:
            coin: Cryptocurrency symbol (default 'BTC').

        Returns:
            True if the daemon is reachable and responding.
        """
        res = await self._rpc_call(coin, "getnetworkinfo")
        return res is not None

    async def get_mempool_fee_rate(
        self, coin: str
    ) -> Optional[Dict[str, int]]:
        """Fetch current network fee rates from mempool APIs.

        APIs used:
        - BTC: mempool.space/api/v1/fees/recommended
        - LTC: blockcypher.com/v1/ltc/main
        - DOGE: sochain.com/api/v2/get_info/DOGE

        Args:
            coin: Cryptocurrency symbol.

        Returns:
            Dict with 'economy', 'normal', and 'priority' fee
            rates in sat/byte, or None if unavailable.
        """
        coin = coin.upper()
        timeout = aiohttp.ClientTimeout(total=10)

        try:
            session = await self._get_session()

            if coin == "BTC":
                url = (
                    "https://mempool.space"
                    "/api/v1/fees/recommended"
                )
                async with session.get(
                    url, timeout=timeout
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {
                            "economy": data.get(
                                "minimumFee", 1
                            ),
                            "normal": data.get(
                                "halfHourFee", 5
                            ),
                            "priority": data.get(
                                "fastestFee", 10
                            ),
                        }

            elif coin == "LTC":
                url = (
                    "https://api.blockcypher.com"
                    "/v1/ltc/main"
                )
                async with session.get(
                    url, timeout=timeout
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # BlockCypher returns sat/kb
                        low_fee = (
                            data.get("low_fee_per_kb", 1000)
                            // 1000
                        )
                        med_fee = (
                            data.get(
                                "medium_fee_per_kb", 5000
                            )
                            // 1000
                        )
                        high_fee = (
                            data.get(
                                "high_fee_per_kb", 10000
                            )
                            // 1000
                        )
                        return {
                            "economy": max(1, low_fee),
                            "normal": max(3, med_fee),
                            "priority": max(5, high_fee),
                        }

            elif coin == "DOGE":
                url = (
                    "https://sochain.com"
                    "/api/v2/get_info/DOGE"
                )
                async with session.get(
                    url, timeout=timeout
                ) as resp:
                    if resp.status == 200:
                        # DOGE has very low fees
                        return {
                            "economy": 1,
                            "normal": 2,
                            "priority": 5,
                        }

            logger.warning(
                "No mempool API configured for %s, "
                "using fallback", coin,
            )
            return None

        except Exception as e:
            logger.warning(
                "Failed to fetch mempool fees for %s: %s",
                coin, e,
            )
            return None

    async def get_network_fee_estimate(
        self, coin: str, priority: str = "economy"
    ) -> Optional[float]:
        """Estimate network fee for a transaction.

        First tries real-time mempool APIs, falls back to
        RPC estimatesmartfee.

        Args:
            coin: Cryptocurrency symbol (BTC, LTC, DOGE).
            priority: Fee priority
                ('economy', 'normal', 'priority').

        Returns:
            Estimated fee in satoshis per byte, or None.
        """
        # Try mempool API first (real-time data)
        mempool_fees = await self.get_mempool_fee_rate(coin)
        if mempool_fees:
            fee = mempool_fees.get(
                priority, mempool_fees.get("normal", 5)
            )
            return float(fee)

        # Fallback to RPC estimation
        blocks = {"economy": 12, "normal": 6, "priority": 2}
        target_blocks = blocks.get(priority, 6)

        result = await self._rpc_call(
            coin, "estimatesmartfee", [target_blocks]
        )
        if result and "feerate" in result:
            # Convert BTC/kB to sat/byte
            return int(
                result["feerate"] * 100_000_000 / 1000
            )
        return None

    def is_off_peak_hour(self) -> bool:
        """Check if current time is optimal for withdrawals.

        Off-peak hours are typically:
        - Late night / early morning UTC (22:00 - 05:00)
        - Weekends (especially Sunday)

        These times generally have lower network congestion
        and fees.

        Returns:
            True if current time is off-peak for withdrawals.
        """
        now = datetime.now(timezone.utc)
        is_night = now.hour >= 22 or now.hour < 5
        is_weekend = now.weekday() >= 5
        return is_night or is_weekend

    async def get_address_balance_api(
        self, coin: str, address: str
    ) -> Optional[float]:
        """Fetch on-chain balance for an address via public APIs.

        Uses lightweight explorer endpoints (read-only) so it
        works for Cake wallet receive-only addresses without
        requiring RPC credentials.

        Args:
            coin: Cryptocurrency symbol.
            address: Wallet address to query.

        Returns:
            Confirmed balance in the main unit
            (BTC/LTC/DOGE/ETH/TRX/etc.), or None for
            unsupported coins (e.g. XMR).
        """
        coin = coin.upper()
        session = await self._get_session()
        timeout = aiohttp.ClientTimeout(total=10)

        try:
            if coin == "BTC":
                url = (
                    "https://api.blockcypher.com/v1"
                    f"/btc/main/addrs/{address}/balance"
                )
                async with session.get(
                    url, timeout=timeout
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        sat = data.get("final_balance", 0)
                        return float(sat) / 1e8

            elif coin == "LTC":
                url = (
                    "https://api.blockcypher.com/v1"
                    f"/ltc/main/addrs/{address}/balance"
                )
                async with session.get(
                    url, timeout=timeout
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        sat = data.get("final_balance", 0)
                        return float(sat) / 1e8

            elif coin == "DOGE":
                url = (
                    "https://sochain.com/api/v2"
                    f"/get_address_balance/DOGE/{address}"
                )
                async with session.get(
                    url, timeout=timeout
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        bal = (
                            data.get("data", {})
                            .get("confirmed_balance")
                        )
                        if bal is not None:
                            return float(bal)
                        return 0.0

            elif coin == "ETH":
                url = (
                    "https://api.blockcypher.com/v1"
                    f"/eth/main/addrs/{address}/balance"
                )
                async with session.get(
                    url, timeout=timeout
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        wei = data.get("final_balance", 0)
                        return float(wei) / 1e18

            elif coin == "TRX":
                url = (
                    "https://apilist.tronscan.org"
                    f"/api/account?address={address}"
                )
                async with session.get(
                    url, timeout=timeout
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        bal = data.get("balance")
                        if bal is not None:
                            return float(bal) / 1e6
                        return 0.0

            elif coin in {"BCH", "DASH"}:
                url = (
                    "https://api.blockcypher.com/v1"
                    f"/{coin.lower()}/main"
                    f"/addrs/{address}/balance"
                )
                async with session.get(
                    url, timeout=timeout
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        sat = data.get("final_balance", 0)
                        return float(sat) / 1e8

            logger.info(
                "No public balance API configured for "
                "%s; returning None", coin,
            )
            return None
        except Exception as exc:
            logger.warning(
                "Failed to fetch address balance "
                "for %s: %s", coin, exc,
            )
            return None

    async def get_balances_for_addresses(
        self, wallet_addresses: Dict[str, Any]
    ) -> Dict[str, float]:
        """Fetch balances for all configured addresses.

        Supports dict entries like ``{"BTC": {"address": "..."}}``
        or ``{"BTC": "addr"}``. Unsupported coins are skipped.

        Args:
            wallet_addresses: Mapping of coin symbols to
                address configs (str or dict with 'address'
                key).

        Returns:
            Dict mapping coin symbols to their balances.
        """
        balances: Dict[str, float] = {}

        for coin, entry in wallet_addresses.items():
            address: Optional[str] = None
            if isinstance(entry, dict):
                address = (
                    entry.get("address")
                    or entry.get("wallet")
                    or entry.get("addr")
                )
            elif isinstance(entry, str):
                address = entry

            if not address:
                continue

            balance = await self.get_address_balance_api(
                coin, address
            )
            if balance is not None:
                balances[coin.upper()] = balance

        return balances

    async def should_withdraw_now(
        self,
        coin: str,
        balance_sat: int,
        min_threshold: int = 30000,
    ) -> bool:
        """Determine if withdrawal should proceed now.

        Uses real-time mempool data for optimal fee timing.

        Args:
            coin: Cryptocurrency symbol.
            balance_sat: Current balance in satoshis.
            min_threshold: Minimum balance required
                (default 30,000 satoshi).

        Returns:
            True if withdrawal is recommended now.
        """
        if balance_sat < min_threshold:
            logger.info(
                "Balance %d sat below threshold %d",
                balance_sat, min_threshold,
            )
            return False

        # Check if off-peak hours
        is_off_peak = self.is_off_peak_hour()
        if not is_off_peak:
            logger.info(
                "Not off-peak hour, checking if fees "
                "are exceptionally low..."
            )

        # Get real-time mempool fee data
        mempool_fees = await self.get_mempool_fee_rate(coin)

        if mempool_fees:
            economy_fee = mempool_fees.get("economy", 999)

            # Excellent fees (< 5 sat/byte) - withdraw now
            if economy_fee < 5:
                logger.info(
                    "Excellent fees (%d sat/byte) "
                    "- proceeding with withdrawal",
                    economy_fee,
                )
                return True

            # Good fees (< 20 sat/byte) during off-peak
            if is_off_peak and economy_fee < 20:
                logger.info(
                    "Good off-peak fees (%d sat/byte) "
                    "- proceeding", economy_fee,
                )
                return True

            # High fees (> 50 sat/byte) - defer
            if economy_fee > 50:
                logger.info(
                    "High network fees (%d sat/byte) "
                    "- deferring withdrawal",
                    economy_fee,
                )
                return False

            # Medium fees off-peak with high balance
            if is_off_peak and balance_sat > min_threshold * 2:
                logger.info(
                    "Medium fees (%d sat/byte) but high "
                    "balance - proceeding", economy_fee,
                )
                return True

        # No mempool data - off-peak only
        if is_off_peak:
            logger.info(
                "Off-peak hour with no fee data "
                "- proceeding conservatively"
            )
            return True

        logger.info(
            "Conditions not optimal for withdrawal "
            "- deferring"
        )
        return False

    async def batch_withdraw(
        self,
        coin: str,
        outputs: List[Dict[str, Any]],
        fee_priority: str = "economy",
    ) -> Optional[str]:
        """Execute batched withdrawal with multiple outputs.

        Batching multiple withdrawals into a single transaction
        can reduce fees by 50-70% compared to individual
        transactions.

        Args:
            coin: Cryptocurrency symbol.
            outputs: List of {"address": str, "amount": float}.
            fee_priority: Fee tier
                ('economy', 'normal', 'priority').

        Returns:
            Transaction ID on success, None on failure.
        """
        from core.withdrawal_analytics import get_analytics

        if not outputs:
            logger.warning(
                "No outputs provided for batch withdrawal"
            )
            return None

        # Validate all addresses first
        for out in outputs:
            is_valid = await self.validate_address(
                out["address"], coin
            )
            if not is_valid:
                logger.error(
                    "Invalid address in batch: %s",
                    out["address"],
                )
                return None

        # Get network fee estimate
        fee_rate = await self.get_network_fee_estimate(
            coin, fee_priority
        )
        # Estimate for typical 250-byte tx size
        estimated_network_fee = (
            (fee_rate * 250 / 1e8) if fee_rate else 0.0
        )

        # Format for sendmany RPC call
        amounts = {
            out["address"]: out["amount"] for out in outputs
        }
        total_amount = sum(
            out["amount"] for out in outputs
        )

        result = await self._rpc_call(
            coin, "sendmany", ["", amounts]
        )

        if result:
            logger.info(
                "Batch withdrawal submitted: txid=%s",
                result,
            )

            # Record in analytics
            try:
                analytics = get_analytics()
                analytics.record_withdrawal(
                    faucet="WalletDaemon",
                    cryptocurrency=coin,
                    amount=total_amount,
                    network_fee=estimated_network_fee,
                    platform_fee=0.0,
                    withdrawal_method="wallet_daemon",
                    status="success",
                    tx_id=result,
                    notes=(
                        "Batch withdrawal with "
                        f"{len(outputs)} outputs"
                    ),
                )
            except Exception as e:
                logger.warning(
                    "Failed to record batch withdrawal "
                    "analytics: %s", e,
                )

            return result

        logger.error("Batch withdrawal failed")
        return None
