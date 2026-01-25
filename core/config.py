import json
# pylint: disable=no-member
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from pydantic import Field, BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from enum import Enum

# Base Paths
BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = BASE_DIR / "config"
LOGS_DIR = BASE_DIR / "logs"

logger = logging.getLogger(__name__)


class OperationMode(Enum):
    """Operation modes for graceful degradation."""
    NORMAL = "normal"  # All systems operational
    LOW_PROXY = "low_proxy"  # <10 healthy proxies
    LOW_BUDGET = "low_budget"  # <$1 captcha budget remaining
    SLOW_MODE = "slow"  # High failure rate detected
    MAINTENANCE = "maintenance"  # Manual mode, finish existing only


class AccountProfile(BaseModel):
    faucet: str
    username: str
    password: str
    proxy: Optional[str] = None
    proxy_pool: List[str] = []  # Multiple proxies for rotation
    proxy_rotation_strategy: str = "round_robin"  # Options: round_robin, random, health_based
    residential_proxy: bool = False  # Flag to indicate if proxies are residential
    enabled: bool = True
    behavior_profile: Optional[str] = None  # Optional timing profile (fast, balanced, cautious)

class BotSettings(BaseSettings):
    """
    Gen 3.0 Configuration
    """
    # Core
    log_level: str = "INFO"
    headless: bool = True
    timeout: int = 180000  # Global timeout in ms (default 180s for slow proxies)
    
    # Security / API
    captcha_provider: str = "2captcha"
    twocaptcha_api_key: Optional[str] = None
    use_2captcha_proxies: bool = True  # Set to True to enable 2Captcha proxy integration
    enable_shortlinks: bool = False  # Enable multi-session shortlink claiming (experimental)
    capsolver_api_key: Optional[str] = None
    captcha_daily_budget: float = 5.0  # Daily spend cap for captcha solving
    captcha_fallback_provider: Optional[str] = None  # Optional fallback provider (e.g., capsolver)
    captcha_fallback_api_key: Optional[str] = None
    
    # Proxy Configuration
    residential_proxies_file: str = str(CONFIG_DIR / "proxies.txt")  # File containing 1 proxy per line (user:pass@ip:port)
    proxy_provider: str = "2captcha"  # Options: 2captcha, webshare, zyte
    webshare_api_key: Optional[str] = None
    webshare_page_size: int = 50
    # Proxy validation/health
    proxy_validation_url: str = "https://www.google.com"  # Lightweight URL for latency checks
    proxy_validation_timeout_seconds: int = 15
    # Zyte proxy (proxy mode). Host/port are for proxy endpoint; protocol can be http/https.
    zyte_api_key: Optional[str] = None
    zyte_proxy_host: str = "api.zyte.com"
    zyte_proxy_port: int = 8011
    zyte_proxy_protocol: str = "http"
    zyte_pool_size: int = 20  # In-memory logical slots for sticky assignment
    # Proxy routing overrides
    proxy_bypass_faucets: List[str] = Field(default_factory=lambda: ["freebitcoin"])
    # Image blocking overrides (allow images for selected faucets)
    image_bypass_faucets: List[str] = Field(default_factory=lambda: ["freebitcoin"])
    
    # Optimization
    block_images: bool = True
    block_media: bool = True

    # Cost Modeling (USD)
    time_cost_per_hour_usd: float = 0.0  # VM/runtime cost per bot-hour
    proxy_cost_per_hour_usd: float = 0.0  # Proxy cost per hour of usage

    # Captcha Provider Routing
    captcha_provider_routing: str = "fixed"  # Options: fixed, adaptive
    captcha_provider_routing_min_samples: int = 20  # Minimum samples before routing adapts

    # Job Watchdog
    job_timeout_seconds: int = 600  # Max time per job before watchdog triggers

    # Time-of-day Optimization
    time_of_day_roi_enabled: bool = True
    time_of_day_roi_weight: float = 0.15  # Weight applied to time-of-day ROI boost

    # Proxy Reputation Scoring
    proxy_reputation_enabled: bool = True
    proxy_reputation_min_score: float = 20.0  # Min score to be considered healthy

    # Alert Routing
    alert_webhook_url: Optional[str] = None  # Optional webhook for health alerts

    # Registration Defaults
    # (Moved to lines 141-146 to avoid duplication)

    # Wallet Infrastructure (Multi-Coin Support)
    # Mapping of coin -> RPC URL
    wallet_rpc_urls: Dict[str, str] = {
        "BTC": "http://127.0.0.1:7777",
        "LTC": "http://127.0.0.1:7778",
        "DOGE": "http://127.0.0.1:7779"
    }
    
    # Withdrawal Addresses (Direct)
    btc_withdrawal_address: Optional[str] = None
    ltc_withdrawal_address: Optional[str] = None
    doge_withdrawal_address: Optional[str] = None
    electrum_rpc_user: Optional[str] = None
    electrum_rpc_pass: Optional[str] = None

    # FaucetPay Integration (Micro-Wallet for Fee Optimization)
    use_faucetpay: bool = True  # Toggle FaucetPay vs Direct withdrawals
    faucetpay_email: Optional[str] = None
    faucetpay_btc_address: Optional[str] = None
    faucetpay_ltc_address: Optional[str] = None
    faucetpay_doge_address: Optional[str] = None
    faucetpay_bch_address: Optional[str] = None
    faucetpay_trx_address: Optional[str] = None
    faucetpay_eth_address: Optional[str] = None
    faucetpay_bnb_address: Optional[str] = None
    faucetpay_sol_address: Optional[str] = None
    faucetpay_ton_address: Optional[str] = None
    faucetpay_dash_address: Optional[str] = None
    faucetpay_polygon_address: Optional[str] = None
    faucetpay_usdt_address: Optional[str] = None

    # Dynamic Withdrawal Thresholds (in satoshis/smallest unit)
    # Format: {"min": minimum before considering, "target": ideal batch size, "max": force withdrawal}
    withdrawal_thresholds: Dict[str, Dict[str, int]] = {
        "BTC": {"min": 5000, "target": 50000, "max": 100000},  # Higher due to network fees
        "LTC": {"min": 1000, "target": 10000, "max": 50000},   # Medium fees
        "DOGE": {"min": 500, "target": 5000, "max": 10000},     # Low fees
        "BCH": {"min": 1000, "target": 10000, "max": 50000},
        "TRX": {"min": 500, "target": 5000, "max": 10000},
        "ETH": {"min": 10000, "target": 100000, "max": 200000},  # High gas fees
        "BNB": {"min": 1000, "target": 10000, "max": 50000},
        "SOL": {"min": 500, "target": 5000, "max": 10000},
        "TON": {"min": 500, "target": 5000, "max": 10000},
        "DASH": {"min": 1000, "target": 10000, "max": 50000},
        "POLYGON": {"min": 500, "target": 5000, "max": 10000},
        "USDT": {"min": 1000, "target": 10000, "max": 50000}
    }

    # Legacy Withdrawal Thresholds (for backward compatibility)
    coinpayu_min_withdraw: int = 2000
    firefaucet_min_withdraw: int = 5000
    dutchycorp_min_withdraw: int = 10000
    faucetcrypto_min_withdraw: int = 1000
    freebitcoin_min_withdraw: int = 30000

    # Withdrawal Timing Strategy
    withdrawal_schedule: str = "off_peak"  # Options: immediate, off_peak, weekly_batch
    off_peak_hours: List[int] = [0, 1, 2, 3, 4, 5, 22, 23]  # UTC hours (low network activity)
    prefer_off_peak_withdrawals: bool = True  # Prefer off-peak hours for withdrawals
    auto_consolidate_to_faucetpay: bool = True  # Auto-transfer from faucets to FaucetPay
    auto_withdraw_from_faucetpay: bool = False  # Requires FaucetPay API (manual for now)
    consolidation_interval_hours: int = 24  # How often to check/consolidate
    withdrawal_retry_intervals: List[int] = [3600, 21600, 86400]  # Retry intervals: 1h, 6h, 24h
    withdrawal_max_retries: int = 3  # Maximum retry attempts before marking as failed

    # Performance / Concurrency
    max_concurrent_bots: int = 3
    max_concurrent_per_profile: int = 1
    scheduler_tick_rate: float = 1.0
    exploration_frequency_minutes: int = 30

    # Degraded operation modes
    low_proxy_threshold: int = 10
    low_proxy_max_concurrent_bots: int = 1
    degraded_failure_threshold: int = 3
    degraded_slow_delay_multiplier: float = 2.0
    performance_alert_slow_threshold: int = 2

    # Canary rollout (optional)
    canary_profile: Optional[str] = Field(default=None, alias="CANARY_PROFILE")
    canary_only: bool = Field(default=False, alias="CANARY_ONLY")
    
    # Auto-Suspend / Circuit Breaker Settings
    faucet_auto_suspend_enabled: bool = True  # Enable ROI-based auto-suspend
    faucet_min_success_rate: float = 30.0  # Suspend if success rate < 30%
    faucet_roi_threshold: float = -0.5  # Suspend if ROI < -0.5 (more costs than earnings)
    faucet_auto_suspend_duration: int = 14400  # 4 hours cooldown for low ROI faucets
    faucet_auto_suspend_min_samples: int = 5  # Minimum claims before auto-suspend
    
    # Browser / stealth - Diverse UA pool for fingerprint rotation
    user_agents: List[str] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:  # pylint: disable=arguments-differ
        """Initialize dynamic user agents if empty."""
        if not self.user_agents:
            try:
                from fake_useragent import UserAgent
                ua = UserAgent(browsers=['chrome', 'edge', 'firefox', 'safari'])
                # Generate a pool of 100 random modern UAs
                self.user_agents = [ua.random for _ in range(100)]
            except Exception:
                # Fallback list if fake-useragent is not installed or can't reach its data source
                self.user_agents = [
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0"
                ]

        self._load_faucet_config_defaults()

    def _load_faucet_config_defaults(self) -> None:
        """
        Load accounts and wallet addresses from config/faucet_config.json
        if not already provided via environment settings.
        """
        config_path = CONFIG_DIR / "faucet_config.json"
        if not config_path.exists():
            return

        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"Failed to load faucet_config.json: {exc}")
            return

        # Merge accounts from config (do not overwrite existing entries)
        accounts_data = data.get("accounts", {})
        if isinstance(accounts_data, dict):
            existing_keys = {
                (acc.faucet.lower().replace("_", "").replace(" ", ""), acc.username)
                for acc in self.accounts
            }
            for faucet, info in accounts_data.items():
                if not isinstance(info, dict):
                    continue
                if not info.get("enabled", True):
                    continue
                username = info.get("username")
                password = info.get("password")
                if not username or not password:
                    continue
                proxy = info.get("proxy")
                key = (str(faucet).lower().replace("_", "").replace(" ", ""), username)
                if key in existing_keys:
                    continue
                try:
                    self.accounts.append(
                        AccountProfile(
                            faucet=faucet,
                            username=username,
                            password=password,
                            proxy=proxy,
                            enabled=info.get("enabled", True),
                            proxy_pool=info.get("proxy_pool", []),
                            proxy_rotation_strategy=info.get("proxy_rotation_strategy", "round_robin"),
                            residential_proxy=info.get("residential_proxy", False),
                            behavior_profile=info.get("behavior_profile")
                        )
                    )
                except Exception as exc:
                    logger.debug(f"Skipping invalid account entry for {faucet}: {exc}")

        if not self.wallet_addresses:
            wallet_addresses = data.get("wallet_addresses")
            if isinstance(wallet_addresses, dict):
                self.wallet_addresses = wallet_addresses

        # Optional: load browser settings from config
        browser_settings = data.get("browser_settings")
        if isinstance(browser_settings, dict):
            if "headless" in browser_settings:
                self.headless = bool(browser_settings.get("headless"))
            if "timeout" in browser_settings:
                self.timeout = int(browser_settings.get("timeout", self.timeout))
            if "block_images" in browser_settings:
                self.block_images = bool(browser_settings.get("block_images"))
            if "block_media" in browser_settings:
                self.block_media = bool(browser_settings.get("block_media"))
            # If a user agent list is provided, use it
            if "user_agents" in browser_settings and isinstance(browser_settings.get("user_agents"), list):
                if browser_settings.get("user_agents"):
                    self.user_agents = browser_settings.get("user_agents")

    # Registration Defaults
    # Registration Defaults - Moved to ensure single definition
    registration_email: Optional[str] = Field(default=None, alias="REGISTRATION_EMAIL")
    registration_password: Optional[str] = Field(default=None, alias="REGISTRATION_PASSWORD")
    registration_username: Optional[str] = Field(default=None, alias="REGISTRATION_USERNAME")
    # Unified proxy string format: protocol://user:pass@host:port
    registration_proxy: Optional[str] = Field(default=None, alias="REGISTRATION_PROXY")

    # Legacy Single Account Credentials (for backward compat)
    firefaucet_username: Optional[str] = None
    firefaucet_password: Optional[str] = None
    
    cointiply_username: Optional[str] = None
    cointiply_password: Optional[str] = None
    
    freebitcoin_username: Optional[str] = None
    freebitcoin_password: Optional[str] = None

    dutchy_username: Optional[str] = None
    dutchy_password: Optional[str] = None
    
    # Pick.io Family Credentials
    litepick_username: Optional[str] = None
    litepick_password: Optional[str] = None
    tronpick_username: Optional[str] = None
    tronpick_password: Optional[str] = None
    dogepick_username: Optional[str] = None
    dogepick_password: Optional[str] = None
    bchpick_username: Optional[str] = None
    bchpick_password: Optional[str] = None
    solpick_username: Optional[str] = None
    solpick_password: Optional[str] = None
    tonpick_username: Optional[str] = None
    tonpick_password: Optional[str] = None
    polygonpick_username: Optional[str] = None
    polygonpick_password: Optional[str] = None
    binpick_username: Optional[str] = None
    binpick_password: Optional[str] = None
    dashpick_username: Optional[str] = None
    dashpick_password: Optional[str] = None
    ethpick_username: Optional[str] = None
    ethpick_password: Optional[str] = None
    usdpick_username: Optional[str] = None
    usdpick_password: Optional[str] = None

    # Multi-Account Profiles
    # This list can be populated from JSON env var or config file
    accounts: List[AccountProfile] = Field(default_factory=list)

    enabled_faucets: List[str] = [
        "fire_faucet", "cointiply", "dutchy",
        "litepick", "tronpick", "dogepick", "solpick", "binpick", 
        "bchpick", "tonpick", "polygonpick", "dashpick", "ethpick", "usdpick"
    ]
    wallet_addresses: Dict[str, str] = Field(default_factory=dict)

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def get_account(self, faucet_name: str) -> Optional[Dict[str, str]]:
        """
        Helper to get the first matching account.
        Prioritizes the 'accounts' list, falls back to legacy fields.
        """
        name = faucet_name.lower().replace("_", "").replace(" ", "")
        
        # Check Profiles First
        for acc in self.accounts:
            acc_name = acc.faucet.lower().replace("_", "").replace(" ", "")
            if acc.enabled and (acc_name == name or acc_name in name or name in acc_name):
                return {"username": acc.username, "password": acc.password, "proxy": acc.proxy}

        # Fallback to Legacy Fields
        if "fire" in name and self.firefaucet_username:
            return {"username": self.firefaucet_username, "password": self.firefaucet_password}
        elif "cointiply" in name and self.cointiply_username:
            return {"username": self.cointiply_username, "password": self.cointiply_password}
        elif "freebitcoin" in name and self.freebitcoin_username:
            return {"username": self.freebitcoin_username, "password": self.freebitcoin_password}
        elif "dutchy" in name and self.dutchy_username:
            return {"username": self.dutchy_username, "password": self.dutchy_password}
        
        # Pick.io Family Fallbacks (use 'email' key for Pick.io sites)
        elif "litepick" in name and self.litepick_username:
            return {"email": self.litepick_username, "password": self.litepick_password}
        elif "tronpick" in name and self.tronpick_username:
            return {"email": self.tronpick_username, "password": self.tronpick_password}
        elif "dogepick" in name and self.dogepick_username:
            return {"email": self.dogepick_username, "password": self.dogepick_password}
        elif "bchpick" in name and self.bchpick_username:
            return {"email": self.bchpick_username, "password": self.bchpick_password}
        elif "solpick" in name and self.solpick_username:
            return {"email": self.solpick_username, "password": self.solpick_password}
        elif "tonpick" in name and self.tonpick_username:
            return {"email": self.tonpick_username, "password": self.tonpick_password}
        elif "polygonpick" in name and self.polygonpick_username:
            return {"email": self.polygonpick_username, "password": self.polygonpick_password}
        elif "binpick" in name and self.binpick_username:
            return {"email": self.binpick_username, "password": self.binpick_password}
        elif "dashpick" in name and self.dashpick_username:
            return {"email": self.dashpick_username, "password": self.dashpick_password}
        elif "ethpick" in name and self.ethpick_username:
            return {"email": self.ethpick_username, "password": self.ethpick_password}
        elif "usdpick" in name and self.usdpick_username:
            return {"email": self.usdpick_username, "password": self.usdpick_password}
        
        return None

    def filter_profiles(self, profiles: List[AccountProfile]) -> List[AccountProfile]:
        """
        Apply canary filtering to profiles when enabled.
        Matches by faucet name or username (case-insensitive substring).
        """
        if not self.canary_only or not self.canary_profile:
            return profiles

        target = self.canary_profile.lower()
        return [
            profile for profile in profiles
            if target in profile.faucet.lower() or target in profile.username.lower()
        ]
