"""Application configuration for Cryptobot Gen 3.0.

Central configuration module powered by Pydantic v2.  Settings are loaded from
environment variables (with ``.env`` file support) and an optional
``config/faucet_config.json`` file.

Key exports:
    BotSettings: Root settings model (singleton-like; instantiate once).
    AccountProfile: Per-faucet credential + proxy model.
    OperationMode: Enum for graceful degradation states.
    BASE_DIR / CONFIG_DIR / LOGS_DIR: Canonical project paths.
"""

# pylint: disable=no-member

import json
import logging
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Base Paths
# ---------------------------------------------------------------------------
BASE_DIR: Path = Path(__file__).parent.parent
"""Project root directory (parent of ``core/``)."""

CONFIG_DIR: Path = BASE_DIR / "config"
"""Directory containing runtime configuration files (proxies, state, cookies)."""

LOGS_DIR: Path = BASE_DIR / "logs"
"""Directory for log output files."""

logger: logging.Logger = logging.getLogger(__name__)


class OperationMode(Enum):
    """Operation modes for graceful degradation.

    Members:
        NORMAL: All systems operational.
        LOW_PROXY: Fewer than 10 healthy proxies available.
        LOW_BUDGET: Less than $1 captcha budget remaining.
        SLOW_MODE: High failure rate detected.
        MAINTENANCE: Manual mode, finish existing jobs only.
    """

    NORMAL = "normal"
    LOW_PROXY = "low_proxy"
    LOW_BUDGET = "low_budget"
    SLOW_MODE = "slow"
    MAINTENANCE = "maintenance"


class AccountProfile(BaseModel):
    """Credentials and proxy configuration for a single faucet account.

    Attributes:
        faucet: Faucet identifier matching a key in ``FAUCET_REGISTRY``.
        username: Login username or email address.
        password: Login password.
        proxy: Optional sticky proxy URL
            (``protocol://user:pass@host:port``).
        proxy_pool: List of proxy URLs available for rotation.
        proxy_rotation_strategy: Rotation algorithm --
            ``round_robin``, ``random``, or ``health_based``.
        residential_proxy: Whether the assigned proxies are residential
            (affects cooldown / burn policies).
        enabled: Set to ``False`` to skip this account during job
            creation.
        behavior_profile: Optional humanisation timing profile name
            (``fast`` / ``balanced`` / ``cautious``).
    """

    faucet: str
    username: str
    password: str
    proxy: Optional[str] = None
    proxy_pool: List[str] = []
    proxy_rotation_strategy: str = "round_robin"
    residential_proxy: bool = False
    enabled: bool = True
    behavior_profile: Optional[str] = None


class BotSettings(BaseSettings):
    """Root configuration model for Cryptobot Gen 3.0.

    All fields can be set via environment variables or a ``.env`` file.
    The model also merges values from ``config/faucet_config.json``
    (accounts, wallet addresses, browser overrides) during post-init.

    Section overview:
        * **Core** -- log level, headless mode, global timeout.
        * **Security / API** -- CAPTCHA provider keys, daily budget,
          fallback.
        * **Proxy** -- provider selection, file paths, validation,
          routing.
        * **Optimisation** -- image/media blocking, cost modelling.
        * **Wallet** -- JSON-RPC endpoints and withdrawal addresses.
        * **FaucetPay** -- micro-wallet integration addresses.
        * **Withdrawal** -- thresholds, scheduling, retry policy.
        * **Performance** -- concurrency limits, scheduler tick rate.
        * **Degraded modes** -- ``LOW_PROXY`` / ``SLOW_MODE``
          thresholds.
        * **Canary** -- optional canary-rollout filtering.
        * **Auto-suspend** -- ROI-based circuit breaker.
        * **Legacy** -- single-account credential fields for backward
          compat.
    """

    # Core
    log_level: str = "INFO"
    headless: bool = True
    # Global timeout in ms (120s - increased for proxy connections)
    timeout: int = 120000

    # Security / API
    captcha_provider: str = "2captcha"
    twocaptcha_api_key: Optional[str] = None
    # Set to True to enable 2Captcha proxy integration
    use_2captcha_proxies: bool = True
    # Enable multi-session shortlink claiming (experimental)
    enable_shortlinks: bool = False
    capsolver_api_key: Optional[str] = None
    captcha_daily_budget: float = 5.0  # Daily spend cap
    # Optional fallback provider (e.g., capsolver)
    captcha_fallback_provider: Optional[str] = None
    captcha_fallback_api_key: Optional[str] = None

    # 2Captcha Proxy Auto-Refresh Settings
    # Enable automatic proxy refresh (opt-in)
    proxy_auto_refresh_enabled: bool = False
    # Recommended interval for scheduled refresh (for reference)
    proxy_auto_refresh_interval_hours: int = 24
    # Minimum healthy proxies before triggering refresh
    proxy_min_healthy_count: int = 50
    proxy_target_count: int = 100  # Target total proxy count
    # Maximum acceptable proxy latency in milliseconds
    proxy_max_latency_ms: float = 3000

    # Proxy Configuration
    # File containing 1 proxy per line (user:pass@ip:port)
    residential_proxies_file: str = str(
        CONFIG_DIR / "proxies.txt"
    )
    # Azure VM proxy list
    azure_proxies_file: str = str(
        CONFIG_DIR / "azure_proxies.txt"
    )
    # Set to True to use Azure VM proxies instead of 2Captcha
    use_azure_proxies: bool = False
    # DigitalOcean Droplet proxy list
    digitalocean_proxies_file: str = str(
        CONFIG_DIR / "digitalocean_proxies.txt"
    )
    # Set to True to use DigitalOcean Droplet proxies
    use_digitalocean_proxies: bool = False
    # Options: 2captcha, webshare, zyte, azure, digitalocean
    proxy_provider: str = "2captcha"
    webshare_api_key: Optional[str] = None
    webshare_page_size: int = 50
    # Proxy validation/health
    # Lightweight URL for latency checks
    proxy_validation_url: str = "https://www.google.com"
    proxy_validation_timeout_seconds: int = 15
    # Zyte proxy (proxy mode). Host/port are for proxy endpoint.
    zyte_api_key: Optional[str] = None
    zyte_proxy_host: str = "api.zyte.com"
    zyte_proxy_port: int = 8011
    zyte_proxy_protocol: str = "http"
    # In-memory logical slots for sticky assignment
    zyte_pool_size: int = 20
    # Proxy routing overrides
    proxy_bypass_faucets: List[str] = Field(
        default_factory=lambda: [
            "freebitcoin", "cointiply", "firefaucet",
        ]
    )
    # Image blocking overrides (allow images for selected faucets)
    image_bypass_faucets: List[str] = Field(
        default_factory=lambda: [
            "freebitcoin", "firefaucet",
        ]
    )

    # Optimization
    block_images: bool = True
    block_media: bool = True

    # Cost Modeling (USD)
    # VM/runtime cost per bot-hour
    time_cost_per_hour_usd: float = 0.0
    # Proxy cost per hour of usage
    proxy_cost_per_hour_usd: float = 0.0

    # Captcha Provider Routing
    # Options: fixed, adaptive
    captcha_provider_routing: str = "fixed"
    # Minimum samples before routing adapts
    captcha_provider_routing_min_samples: int = 20

    # Job Watchdog
    # Max time per job before watchdog triggers
    job_timeout_seconds: int = 600

    # Time-of-day Optimization
    time_of_day_roi_enabled: bool = True
    # Weight applied to time-of-day ROI boost
    time_of_day_roi_weight: float = 0.15

    # Proxy Reputation Scoring
    proxy_reputation_enabled: bool = True
    # Min score to be considered healthy
    proxy_reputation_min_score: float = 20.0

    # Alert Routing
    # Optional webhook for health alerts
    alert_webhook_url: Optional[str] = None

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
    # Prefer config wallet_addresses (e.g., Cake)
    # over FaucetPay
    prefer_wallet_addresses: bool = True

    # FaucetPay Integration (Micro-Wallet for Fee Optimization)
    # Toggle FaucetPay vs Direct withdrawals
    use_faucetpay: bool = True
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
    # Format: {"min": minimum before considering,
    # "target": ideal batch size, "max": force withdrawal}
    withdrawal_thresholds: Dict[str, Dict[str, int]] = {
        "BTC": {"min": 5000, "target": 50000, "max": 100000},
        "LTC": {"min": 1000, "target": 10000, "max": 50000},
        "DOGE": {"min": 500, "target": 5000, "max": 10000},
        "BCH": {"min": 1000, "target": 10000, "max": 50000},
        "TRX": {"min": 500, "target": 5000, "max": 10000},
        "ETH": {"min": 10000, "target": 100000, "max": 200000},
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
    # Options: immediate, off_peak, weekly_batch
    withdrawal_schedule: str = "off_peak"
    # UTC hours (low network activity)
    off_peak_hours: List[int] = [0, 1, 2, 3, 4, 5, 22, 23]
    # Prefer off-peak hours for withdrawals
    prefer_off_peak_withdrawals: bool = True
    # Auto-transfer from faucets to FaucetPay
    auto_consolidate_to_faucetpay: bool = True
    # Requires FaucetPay API (manual for now)
    auto_withdraw_from_faucetpay: bool = False
    # How often to check/consolidate
    consolidation_interval_hours: int = 24
    # Retry intervals: 1h, 6h, 24h
    withdrawal_retry_intervals: List[int] = [
        3600, 21600, 86400,
    ]
    withdrawal_max_retries: int = 3

    # Performance / Concurrency
    # TEMPORARILY SET TO 1 TO TEST CONCURRENCY ISSUE
    max_concurrent_bots: int = 1
    max_concurrent_per_profile: int = 1
    scheduler_tick_rate: float = 1.0
    exploration_frequency_minutes: int = 30

    # Degraded operation modes
    # LOW_PROXY mode triggers when healthy proxies fall below
    # this threshold.
    # Current setup: 3 DigitalOcean droplets = LOW_PROXY mode
    # (increase DO limit or add Azure VMs to scale)
    # Healthy proxies needed for NORMAL mode
    low_proxy_threshold: int = 10
    # Reduced concurrency in LOW_PROXY mode
    # (was 1, increased to 2 for 3-proxy setup)
    low_proxy_max_concurrent_bots: int = 2
    degraded_failure_threshold: int = 3
    degraded_slow_delay_multiplier: float = 2.0
    performance_alert_slow_threshold: int = 2

    # Canary rollout (optional)
    canary_profile: Optional[str] = Field(
        default=None, alias="CANARY_PROFILE"
    )
    canary_only: bool = Field(
        default=False, alias="CANARY_ONLY"
    )

    # Direct Connection Fallback
    # Enable fallback to direct connection when proxies fail
    enable_direct_fallback: bool = Field(
        default=True, alias="ENABLE_DIRECT_FALLBACK"
    )
    # Number of proxy failures before trying direct connection
    proxy_fallback_threshold: int = Field(
        default=2, alias="PROXY_FALLBACK_THRESHOLD"
    )

    # Auto-Suspend / Circuit Breaker Settings
    # Enable ROI-based auto-suspend
    faucet_auto_suspend_enabled: bool = True
    # Suspend if success rate < 30%
    faucet_min_success_rate: float = 30.0
    # Suspend if ROI < -0.5 (more costs than earnings)
    faucet_roi_threshold: float = -0.5
    # 4 hours cooldown for low ROI faucets
    faucet_auto_suspend_duration: int = 14400
    # Minimum claims before auto-suspend
    faucet_auto_suspend_min_samples: int = 5

    # Browser / stealth - Diverse UA pool for fingerprint rotation
    user_agents: List[str] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        """Initialize dynamic fields after Pydantic model construction.

        * Generates a pool of user-agent strings (via
          ``fake_useragent`` or a hardcoded fallback list) if none
          were supplied.
        * Loads supplementary accounts and wallet addresses from
          ``config/faucet_config.json``.
        """
        if not self.user_agents:
            try:
                from fake_useragent import UserAgent
                ua = UserAgent(
                    browsers=['chrome', 'edge', 'firefox', 'safari']
                )
                # Generate a pool of 100 random modern UAs
                self.user_agents = [
                    ua.random for _ in range(100)
                ]
            except Exception:
                # Fallback list if fake-useragent is not installed
                # or cannot reach its data source
                self.user_agents = [
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/119.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X "
                    "10_15_7) AppleWebKit/537.36 (KHTML, like "
                    "Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; "
                    "x64; rv:121.0) "
                    "Gecko/20100101 Firefox/121.0",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X "
                    "10.15; rv:121.0) "
                    "Gecko/20100101 Firefox/121.0",
                ]

        self._load_faucet_config_defaults()

    def _load_faucet_config_defaults(self) -> None:
        """Load accounts and wallet addresses from config file.

        Reads ``config/faucet_config.json`` and merges its contents
        into the current settings instance.

        Accounts already present (matched by normalised faucet name
        + username) are *not* overwritten.  Browser-level overrides
        (headless, timeout, block_images, block_media, user_agents)
        are applied only when the JSON file provides them.
        """
        config_path: Path = CONFIG_DIR / "faucet_config.json"
        if not config_path.exists():
            return

        try:
            data: Dict[str, Any] = json.loads(
                config_path.read_text(encoding="utf-8")
            )
        except Exception as exc:
            logger.warning(
                "Failed to load faucet_config.json: %s", exc
            )
            return

        # Merge accounts from config (do not overwrite existing)
        accounts_data = data.get("accounts", {})
        if isinstance(accounts_data, dict):
            existing_keys = {
                (
                    acc.faucet.lower()
                    .replace("_", "")
                    .replace(" ", ""),
                    acc.username,
                )
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
                key = (
                    str(faucet).lower()
                    .replace("_", "")
                    .replace(" ", ""),
                    username,
                )
                if key in existing_keys:
                    continue
                try:
                    self.accounts.append(
                        AccountProfile(
                            faucet=faucet,
                            username=username,
                            password=password,
                            proxy=proxy,
                            enabled=info.get(
                                "enabled", True
                            ),
                            proxy_pool=info.get(
                                "proxy_pool", []
                            ),
                            proxy_rotation_strategy=info.get(
                                "proxy_rotation_strategy",
                                "round_robin",
                            ),
                            residential_proxy=info.get(
                                "residential_proxy", False
                            ),
                            behavior_profile=info.get(
                                "behavior_profile"
                            ),
                        )
                    )
                except Exception as exc:
                    logger.debug(
                        "Skipping invalid account entry "
                        "for %s: %s",
                        faucet,
                        exc,
                    )

        if not self.wallet_addresses:
            wallet_addresses = data.get("wallet_addresses")
            if isinstance(wallet_addresses, dict):
                self.wallet_addresses = wallet_addresses

        # Optional: load browser settings from config
        browser_settings = data.get("browser_settings")
        if isinstance(browser_settings, dict):
            if "headless" in browser_settings:
                self.headless = bool(
                    browser_settings.get("headless")
                )
            if "timeout" in browser_settings:
                self.timeout = int(
                    browser_settings.get(
                        "timeout", self.timeout
                    )
                )
            if "block_images" in browser_settings:
                self.block_images = bool(
                    browser_settings.get("block_images")
                )
            if "block_media" in browser_settings:
                self.block_media = bool(
                    browser_settings.get("block_media")
                )
            # If a user agent list is provided, use it
            ua_setting = browser_settings.get("user_agents")
            if isinstance(ua_setting, list) and ua_setting:
                self.user_agents = ua_setting

    # Registration Defaults
    registration_email: Optional[str] = Field(
        default=None, alias="REGISTRATION_EMAIL"
    )
    registration_password: Optional[str] = Field(
        default=None, alias="REGISTRATION_PASSWORD"
    )
    registration_username: Optional[str] = Field(
        default=None, alias="REGISTRATION_USERNAME"
    )
    # Unified proxy string: protocol://user:pass@host:port
    registration_proxy: Optional[str] = Field(
        default=None, alias="REGISTRATION_PROXY"
    )

    # Legacy Single Account Credentials (for backward compat)
    firefaucet_username: Optional[str] = None
    firefaucet_password: Optional[str] = None

    cointiply_username: Optional[str] = None
    cointiply_password: Optional[str] = None

    freebitcoin_username: Optional[str] = None
    freebitcoin_password: Optional[str] = None

    coinpayu_username: Optional[str] = None
    coinpayu_password: Optional[str] = None

    faucetcrypto_username: Optional[str] = None
    faucetcrypto_password: Optional[str] = None

    adbtc_username: Optional[str] = None
    adbtc_password: Optional[str] = None

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
    accounts: List[AccountProfile] = Field(
        default_factory=list
    )

    enabled_faucets: List[str] = [
        "fire_faucet", "cointiply", "dutchy",
        "freebitcoin", "coinpayu", "faucetcrypto",
        "litepick", "tronpick", "dogepick", "solpick",
        "binpick", "bchpick", "tonpick", "polygonpick",
        "dashpick", "ethpick", "usdpick",
    ]
    wallet_addresses: Dict[str, str] = Field(
        default_factory=dict
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def get_account(
        self, faucet_name: str
    ) -> Optional[Dict[str, str]]:
        """Return credentials for the first matching account.

        Lookup order:
            1. ``self.accounts`` list (multi-account profiles).
            2. Legacy per-faucet env-var fields.

        For Pick.io family faucets the returned dict uses an
        ``email`` key instead of ``username``.

        Args:
            faucet_name: Faucet identifier (case-insensitive,
                underscores ignored).

        Returns:
            ``{"username": ..., "password": ...}`` dict, or
            ``None`` if no match is found.
        """
        name: str = (
            faucet_name.lower()
            .replace("_", "")
            .replace(" ", "")
        )

        # Check Profiles First
        for acc in self.accounts:
            acc_name = (
                acc.faucet.lower()
                .replace("_", "")
                .replace(" ", "")
            )
            if acc.enabled and (
                acc_name == name
                or acc_name in name
                or name in acc_name
            ):
                return {
                    "username": acc.username,
                    "password": acc.password,
                    "proxy": acc.proxy,
                }

        # Fallback to Legacy Fields
        if "fire" in name and self.firefaucet_username:
            return {
                "username": self.firefaucet_username,
                "password": self.firefaucet_password,
            }
        if "cointiply" in name and self.cointiply_username:
            return {
                "username": self.cointiply_username,
                "password": self.cointiply_password,
            }
        if "freebitcoin" in name and self.freebitcoin_username:
            return {
                "username": self.freebitcoin_username,
                "password": self.freebitcoin_password,
            }
        if "dutchy" in name and self.dutchy_username:
            return {
                "username": self.dutchy_username,
                "password": self.dutchy_password,
            }
        if "coinpayu" in name and self.coinpayu_username:
            return {
                "username": self.coinpayu_username,
                "password": self.coinpayu_password,
            }
        if "faucetcrypto" in name and self.faucetcrypto_username:
            return {
                "username": self.faucetcrypto_username,
                "password": self.faucetcrypto_password,
            }
        if "adbtc" in name and self.adbtc_username:
            return {
                "username": self.adbtc_username,
                "password": self.adbtc_password,
            }

        # Pick.io Family Fallbacks (use 'email' key)
        if "litepick" in name and self.litepick_username:
            return {
                "email": self.litepick_username,
                "password": self.litepick_password,
            }
        if "tronpick" in name and self.tronpick_username:
            return {
                "email": self.tronpick_username,
                "password": self.tronpick_password,
            }
        if "dogepick" in name and self.dogepick_username:
            return {
                "email": self.dogepick_username,
                "password": self.dogepick_password,
            }
        if "bchpick" in name and self.bchpick_username:
            return {
                "email": self.bchpick_username,
                "password": self.bchpick_password,
            }
        if "solpick" in name and self.solpick_username:
            return {
                "email": self.solpick_username,
                "password": self.solpick_password,
            }
        if "tonpick" in name and self.tonpick_username:
            return {
                "email": self.tonpick_username,
                "password": self.tonpick_password,
            }
        if "polygonpick" in name and self.polygonpick_username:
            return {
                "email": self.polygonpick_username,
                "password": self.polygonpick_password,
            }
        if "binpick" in name and self.binpick_username:
            return {
                "email": self.binpick_username,
                "password": self.binpick_password,
            }
        if "dashpick" in name and self.dashpick_username:
            return {
                "email": self.dashpick_username,
                "password": self.dashpick_password,
            }
        if "ethpick" in name and self.ethpick_username:
            return {
                "email": self.ethpick_username,
                "password": self.ethpick_password,
            }
        if "usdpick" in name and self.usdpick_username:
            return {
                "email": self.usdpick_username,
                "password": self.usdpick_password,
            }

        return None

    def filter_profiles(
        self, profiles: List[AccountProfile]
    ) -> List[AccountProfile]:
        """Apply canary-rollout filtering to a list of profiles.

        When ``canary_only`` is enabled, only profiles whose faucet
        name or username contains ``canary_profile``
        (case-insensitive substring match) are returned.

        Args:
            profiles: Full list of account profiles to filter.

        Returns:
            Filtered list (may be empty if nothing matches).
        """
        if not self.canary_only or not self.canary_profile:
            return profiles

        target: str = self.canary_profile.lower()
        return [
            profile for profile in profiles
            if target in profile.faucet.lower()
            or target in profile.username.lower()
        ]
