"""
Faucets module for Cryptobot Gen 3.0.

Each faucet bot inherits from :class:`FaucetBot` (defined in ``base.py``) and
implements the ``login``, ``get_balance``, ``get_timer``, and ``claim`` async
methods.  Results are returned as :class:`ClaimResult` dataclasses.

The Pick.io family (LitePick, TronPick, DogePick, …) shares a common
:class:`PickFaucetBase` superclass (``pick_base.py``) that provides login,
registration, Cloudflare handling, and navigation-retry logic.

Submodules:
    base: ``FaucetBot`` abstract base, ``ClaimResult`` dataclass.
    pick_base: ``PickFaucetBase`` shared base for all ``*pick.io`` sites.
    firefaucet: ``FireFaucetBot`` – firefaucet.win implementation.
    cointiply: ``CointiplyBot`` – cointiply.com implementation.
    freebitcoin: ``FreeBitcoinBot`` – freebitco.in implementation.
    dutchy: ``DutchyBot`` – dutchycorp.space implementation.
    coinpayu: ``CoinPayUBot`` – coinpayu.com implementation.
    adbtc: ``AdBTCBot`` – adbtc.top implementation.
    faucetcrypto: ``FaucetCryptoBot`` – faucetcrypto.com implementation.
    litepick: ``LitePickBot`` – litepick.io (LTC).
    tronpick: ``TronPickBot`` – tronpick.io (TRX).
    dogepick: ``DogePickBot`` – dogepick.io (DOGE).
    solpick: ``SolPickBot`` – solpick.io (SOL).
    binpick: ``BinPickBot`` – binpick.io (BNB).
    bchpick: ``BchPickBot`` – bchpick.io (BCH).
    tonpick: ``TonPickBot`` – tonpick.io (TON).
    polygonpick: ``PolygonPickBot`` – polygonpick.io (MATIC).
    dashpick: ``DashPickBot`` – dashpick.io (DASH).
    ethpick: ``EthPickBot`` – ethpick.io (ETH).
    usdpick: ``UsdPickBot`` – usdpick.io (USDT).
"""

from .base import FaucetBot, ClaimResult
from .firefaucet import FireFaucetBot
from .cointiply import CointiplyBot
from .dutchy import DutchyBot
from .freebitcoin import FreeBitcoinBot
from .coinpayu import CoinPayUBot
from .adbtc import AdBTCBot
from .faucetcrypto import FaucetCryptoBot
from .litepick import LitePickBot
from .tronpick import TronPickBot
from .dogepick import DogePickBot
from .solpick import SolPickBot
from .binpick import BinPickBot
from .bchpick import BchPickBot
from .tonpick import TonPickBot
from .polygonpick import PolygonPickBot
from .dashpick import DashPickBot
from .ethpick import EthPickBot
from .usdpick import UsdPickBot

__all__ = [
    "FaucetBot",
    "ClaimResult",
    "FireFaucetBot",
    "CointiplyBot",
    "DutchyBot",
    "FreeBitcoinBot",
    "CoinPayUBot",
    "AdBTCBot",
    "FaucetCryptoBot",
    "LitePickBot",
    "TronPickBot",
    "DogePickBot",
    "SolPickBot",
    "BinPickBot",
    "BchPickBot",
    "TonPickBot",
    "PolygonPickBot",
    "DashPickBot",
    "EthPickBot",
    "UsdPickBot",
]
