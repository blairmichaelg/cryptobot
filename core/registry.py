"""Faucet bot factory registry for Cryptobot Gen 3.0.

Maps human-friendly faucet identifiers to their implementing bot classes.
Direct imports are used for core faucets; Pick.io family bots are lazy-loaded
via dotted-path strings to avoid heavyweight import chains at startup.

Usage::

    from core.registry import get_faucet_class

    cls = get_faucet_class("firefaucet")
    if cls:
        bot = cls(settings, page)
"""

from typing import Dict, Optional, Type, Union
from faucets.firefaucet import FireFaucetBot
from faucets.cointiply import CointiplyBot
from faucets.freebitcoin import FreeBitcoinBot
from faucets.dutchy import DutchyBot
from faucets.coinpayu import CoinPayUBot
from faucets.adbtc import AdBTCBot
from faucets.faucetcrypto import FaucetCryptoBot

# ---------------------------------------------------------------------------
# Central Registry
# ---------------------------------------------------------------------------
# Values are either a class reference (eagerly imported) or a dotted-path
# string ``"module.ClassName"`` that is resolved lazily on first use.
FAUCET_REGISTRY: Dict[str, Union[type, str]] = {
    "fire_faucet": FireFaucetBot,
    "firefaucet": FireFaucetBot,
    "fire": FireFaucetBot,
    "cointiply": CointiplyBot,
    "freebitcoin": FreeBitcoinBot,
    "free": FreeBitcoinBot,
    "dutchy": DutchyBot,
    "dutchycorp": DutchyBot,
    "coinpayu": CoinPayUBot,
    "adbtc": AdBTCBot,
    "faucetcrypto": FaucetCryptoBot,
    # Pick Family (.io) - Lazy loaded via string path in main, but we can import here if no circular deps
    # For robust registry, let's keep strings for now if imports are heavy
    "litepick": "faucets.litepick.LitePickBot",
    "tronpick": "faucets.tronpick.TronPickBot",
    "dogepick": "faucets.dogepick.DogePickBot",
    "bchpick": "faucets.bchpick.BchPickBot",
    "solpick": "faucets.solpick.SolPickBot",
    "tonpick": "faucets.tonpick.TonPickBot",
    "polygonpick": "faucets.polygonpick.PolygonPickBot",
    "binpick": "faucets.binpick.BinPickBot",
    "dashpick": "faucets.dashpick.DashPickBot",
    "ethpick": "faucets.ethpick.EthPickBot",
    "usdpick": "faucets.usdpick.UsdPickBot",
}

def get_faucet_class(faucet_type: str) -> Optional[type]:
    """Resolve a faucet bot class from the registry by name.

    Performs case-insensitive lookup.  If the registry value is a dotted-path
    string (e.g. ``"faucets.litepick.LitePickBot"``), the module is imported
    lazily and the class attribute is returned.

    Args:
        faucet_type: Faucet identifier (e.g. ``"firefaucet"``, ``"litepick"``).

    Returns:
        The bot class, or ``None`` if *faucet_type* is not registered.
    """
    cls_or_str = FAUCET_REGISTRY.get(faucet_type.lower())
    if not cls_or_str:
        return None
        
    if isinstance(cls_or_str, str):
        import importlib
        module_path, class_name = cls_or_str.rsplit('.', 1)
        module = importlib.import_module(module_path)
        return getattr(module, class_name)
    
    return cls_or_str
