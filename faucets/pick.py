"""Generic Pick-family faucet bot and factory for Cryptobot Gen 3.0.

Provides :class:`PickFaucetBot` for dynamically instantiating any Pick.io
site by name and URL, and :func:`get_pick_faucets` as a convenience factory
that returns all known Pick.io bots.

Primarily used by the registration script and batch-testing utilities.
"""

from .pick_base import PickFaucetBase
import logging
from typing import List

logger = logging.getLogger(__name__)


class PickFaucetBot(PickFaucetBase):
    """Generic Pick.io family bot instantiated by site name and URL.

    This class is used when a specific per-coin subclass is not needed
    (e.g. bulk registration or testing).  For production claiming, prefer
    the dedicated subclasses (``LitePickBot``, ``TronPickBot``, etc.).
    """
    def __init__(self, settings, page, site_name, site_url, **kwargs):
        super().__init__(settings, page, **kwargs)
        self.faucet_name = site_name
        self.base_url = site_url
        self.coin = site_name.replace("Pick", "").upper()

def get_pick_faucets(settings, page) -> List[PickFaucetBot]:
    """Create instances of all known Pick.io family faucets.

    Args:
        settings: Global :class:`BotSettings` configuration.
        page: Playwright ``Page`` instance shared across bots.

    Returns:
        List of :class:`PickFaucetBot` instances, one per Pick.io site.
    """
    sites = [
        ("LitePick", "https://litepick.io"),
        ("TronPick", "https://tronpick.io"),
        ("DogePick", "https://dogepick.io"),
        ("SolPick", "https://solpick.io"),
        ("BinPick", "https://binpick.io"),
        ("BchPick", "https://bchpick.io"),
        ("TonPick", "https://tonpick.io"),
        ("PolygonPick", "https://polygonpick.io"),
        ("DashPick", "https://dashpick.io"),
        ("EthPick", "https://ethpick.io"),
        ("UsdPick", "https://usdpick.io"),
    ]
    return [PickFaucetBot(settings, page, name, url) for name, url in sites]
