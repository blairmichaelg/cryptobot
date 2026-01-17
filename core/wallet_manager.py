import aiohttp
import logging
import json
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class WalletDaemon:
    """
    Interface for local crypto wallet daemons (Electrum, Core).
    Uses JSON-RPC to manage keys and sign transactions headless.
    """
    
    def __init__(self, rpc_urls: Dict[str, str], rpc_user: str, rpc_pass: str):
        """
        Initialize the WalletDaemon.

        Args:
            rpc_urls: Mapping of coin symbols to their RPC URLs (e.g. {'BTC': 'http://...', 'LTC': '...'}).
            rpc_user: The username for RPC authentication.
            rpc_pass: The password for RPC authentication.
        """
        self.urls = rpc_urls
        self.auth = aiohttp.BasicAuth(rpc_user, rpc_pass) if rpc_user else None
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(auth=self.auth)
        return self._session

    async def _rpc_call(self, coin: str, method: str, params: list = []) -> Any:
        """
        Execute a JSON-RPC call to a specific coin wallet daemon.
        """
        url = self.urls.get(coin.upper())
        if not url:
            logger.error(f"No RPC URL configured for coin: {coin}")
            return None

        payload = {
            "jsonrpc": "2.0",
            "id": f"crypto-bot-{coin}",
            "method": method,
            "params": params
        }
        
        try:
            session = await self._get_session()
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'error' in data and data['error']:
                        logger.error(f"RPC Error {coin}:{method}: {data['error']}")
                        return None
                    return data.get('result')
                else:
                    logger.error(f"RPC HTTP Error {response.status} on {coin}")
                    return None
        except Exception as e:
            logger.error(f"Wallet Daemon Connection Failed ({coin}): {e}")
            return None

    async def get_balance(self, coin: str = "BTC") -> Optional[Dict]:
        """Get confirmed and unconfirmed balance for a specific coin."""
        return await self._rpc_call(coin, "getbalance")

    async def close(self):
        if self._session:
            await self._session.close()

    async def get_unused_address(self, coin: str = "BTC") -> Optional[str]:
        """Generate a new receiving address."""
        return await self._rpc_call(coin, "getunusedaddress")

    async def validate_address(self, address: str) -> bool:
        """Check if address is valid."""
        res = await self._rpc_call("validateaddress", [address])
        return res if isinstance(res, bool) else res.get('isvalid', False)

    async def check_connection(self) -> bool:
        """Health check."""
        res = await self._rpc_call("version")
        return res is not None
