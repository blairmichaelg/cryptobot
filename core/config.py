from pathlib import Path
from typing import Dict, List, Optional, Any
from pydantic import Field, BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base Paths
BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = BASE_DIR / "config"
LOGS_DIR = BASE_DIR / "logs"

class AccountProfile(BaseModel):
    faucet: str
    username: str
    password: str
    proxy: Optional[str] = None
    proxy_pool: List[str] = []  # Multiple proxies for rotation
    proxy_rotation_strategy: str = "round_robin"  # Options: round_robin, random, health_based
    residential_proxy: bool = False  # Flag to indicate if proxies are residential
    enabled: bool = True

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
    capsolver_api_key: Optional[str] = None
    
    # Proxy Configuration
    residential_proxies_file: str = str(CONFIG_DIR / "proxies.txt")  # File containing 1 proxy per line (user:pass@ip:port)
    
    # Optimization
    block_images: bool = True
    block_media: bool = True

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

    def model_post_init(self, __context: Any) -> None:
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
        name = faucet_name.lower().replace("_", "")
        
        # Check Profiles First
        for acc in self.accounts:
            if acc.enabled and acc.faucet.lower() in name:
                return {"username": acc.username, "password": acc.password, "proxy": acc.proxy}

        # Fallback to Legacy
        if "fire" in name and self.firefaucet_username:
            return {"username": self.firefaucet_username, "password": self.firefaucet_password}
        elif "cointiply" in name and self.cointiply_username:
            return {"username": self.cointiply_username, "password": self.cointiply_password}
        elif "freebitcoin" in name and self.freebitcoin_username:
            return {"username": self.freebitcoin_username, "password": self.freebitcoin_password}
        elif "dutchy" in name and self.dutchy_username:
            return {"username": self.dutchy_username, "password": self.dutchy_password}
        
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
