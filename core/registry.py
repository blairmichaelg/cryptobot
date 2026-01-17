from faucets.firefaucet import FireFaucetBot
from faucets.cointiply import CointiplyBot
from faucets.freebitcoin import FreeBitcoinBot
from faucets.dutchy import DutchyBot
from faucets.coinpayu import CoinPayUBot
from faucets.adbtc import AdBTCBot
from faucets.faucetcrypto import FaucetCryptoBot

# Central Registry
FAUCET_REGISTRY = {
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

def get_faucet_class(faucet_type: str):
    """Resolve faucet class from registry."""
    cls_or_str = FAUCET_REGISTRY.get(faucet_type.lower())
    if not cls_or_str:
        return None
        
    if isinstance(cls_or_str, str):
        import importlib
        module_path, class_name = cls_or_str.rsplit('.', 1)
        module = importlib.import_module(module_path)
        return getattr(module, class_name)
    
    return cls_or_str
