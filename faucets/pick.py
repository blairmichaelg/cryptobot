from .pick_base import PickFaucetBase
import logging
from typing import List

logger = logging.getLogger(__name__)

class PickFaucetBot(PickFaucetBase):
    """
    Standard implementation for the 'Pick' family of faucets
    (LitePick, TronPick, DogePick, etc.)
    
    This class is primarily used by the registration script to instantiate
    a bot for a specific site dynamically.
    """
    def __init__(self, settings, page, site_name, site_url, **kwargs):
        super().__init__(settings, page, **kwargs)
        self.faucet_name = site_name
        self.base_url = site_url
        self.coin = site_name.replace("Pick", "").upper()

def get_pick_faucets(settings, page) -> List[PickFaucetBot]:
    """Factory to create all Pick faucets."""
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
