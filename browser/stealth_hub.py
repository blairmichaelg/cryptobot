"""Stealth and anti-detection hub for browser automation.

Provides two main abstractions:

:class:`HumanProfile`
    Timing distributions that simulate distinct human behaviour
    archetypes (fast typist, cautious reader, distracted multi-tasker,
    etc.).  Every faucet bot selects a profile at the start of a session
    and derives all micro-delays from it so that the timing pattern is
    internally consistent.

:class:`StealthHub`
    One-stop shop for stealth artefacts injected into every Camoufox
    browser context: comprehensive JS stealth scripts (canvas, WebGL,
    audio, navigator spoofing), randomised viewport/screen dimensions,
    user-agent pools, pre-navigation warmup routines, and
    locale/timezone/platform consistency helpers.
"""

import random
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class HumanProfile:
    """Human behavioural timing profiles for stealth automation.

    Each class constant (``FAST_USER``, ``NORMAL_USER``, etc.) names a
    distinct behaviour archetype.  The :data:`TIMING_RANGES` dict maps
    every archetype to per-action ``(min, max)`` delay ranges in
    seconds.

    Typical usage::

        profile = HumanProfile.get_random_profile()
        delay   = HumanProfile.get_action_delay(profile, 'click')
        await asyncio.sleep(delay)
    """

    FAST_USER = "fast"
    NORMAL_USER = "normal"
    CAUTIOUS_USER = "cautious"
    DISTRACTED_USER = "distracted"

    ALL_PROFILES = [
        FAST_USER, NORMAL_USER, CAUTIOUS_USER, DISTRACTED_USER,
    ]

    # Action-specific timing ranges per profile (min, max in seconds)
    TIMING_RANGES: Dict[str, Dict[str, Tuple[float, float]]] = {
        FAST_USER: {
            "click": (0.3, 1.0),
            "type": (0.05, 0.15),  # Per character
            "scroll": (0.2, 0.8),
            "read": (0.5, 2.0),
            "thinking": (0.5, 1.5),
        },
        NORMAL_USER: {
            "click": (1.0, 3.0),
            "type": (0.08, 0.20),
            "scroll": (1.0, 2.5),
            "read": (2.0, 5.0),
            "thinking": (2.0, 4.0),
        },
        CAUTIOUS_USER: {
            "click": (2.0, 5.0),
            "type": (0.10, 0.25),
            "scroll": (2.0, 4.0),
            "read": (5.0, 15.0),
            "thinking": (3.0, 8.0),
        },
        DISTRACTED_USER: {
            "click": (1.5, 4.0),
            "type": (0.08, 0.30),
            "scroll": (1.0, 3.0),
            "read": (3.0, 10.0),
            "thinking": (2.0, 6.0),
        },
    }

    @staticmethod
    def get_random_profile() -> str:
        """Return a random profile with weighted distribution.

        Weight distribution favours ``NORMAL_USER`` (50 %) and
        ``CAUTIOUS_USER`` (25 %), followed by ``FAST_USER`` (15 %)
        and ``DISTRACTED_USER`` (10 %).

        Returns:
            One of the profile name constants.
        """
        # FAST, NORMAL, CAUTIOUS, DISTRACTED
        weights = [15, 50, 25, 10]
        return random.choices(
            HumanProfile.ALL_PROFILES, weights=weights, k=1,
        )[0]

    @staticmethod
    def get_action_delay(
        profile: str,
        action_type: str = "click",
    ) -> float:
        """Get delay for a specific action type based on profile.

        Args:
            profile: User profile type
                (fast/normal/cautious/distracted).
            action_type: Action type (click/type/scroll/read).

        Returns:
            Delay in seconds.
        """
        if profile not in HumanProfile.TIMING_RANGES:
            profile = HumanProfile.NORMAL_USER

        if action_type not in HumanProfile.TIMING_RANGES[profile]:
            action_type = "click"

        min_delay, max_delay = (
            HumanProfile.TIMING_RANGES[profile][action_type]
        )

        # Add profile-specific variance
        if profile == HumanProfile.FAST_USER:
            # 20% chance of burst mode (very fast)
            if random.random() < 0.20:
                return random.uniform(0.1, 0.3)
        if profile == HumanProfile.CAUTIOUS_USER:
            # Occasional extra-long pauses (10% chance)
            if random.random() < 0.10:
                return random.uniform(max_delay, max_delay * 2)

        return random.uniform(min_delay, max_delay)

    @staticmethod
    def get_thinking_pause(profile: str) -> float:
        """Get realistic "thinking" pause before important actions.

        Args:
            profile: User profile type.

        Returns:
            Delay in seconds.
        """
        return HumanProfile.get_action_delay(profile, "thinking")

    @staticmethod
    def should_idle(profile: str) -> Tuple[bool, float]:
        """Determine if user should pause (simulates distraction).

        Args:
            profile: User profile type.

        Returns:
            Tuple of (should_pause, pause_duration_seconds).
        """
        idle_probabilities = {
            HumanProfile.FAST_USER: 0.05,
            HumanProfile.NORMAL_USER: 0.10,
            HumanProfile.CAUTIOUS_USER: 0.15,
            HumanProfile.DISTRACTED_USER: 0.30,
        }

        prob = idle_probabilities.get(profile, 0.10)

        if random.random() < prob:
            if profile == HumanProfile.DISTRACTED_USER:
                # Longer distraction periods
                duration = random.uniform(10, 60)
            elif profile == HumanProfile.CAUTIOUS_USER:
                # Moderate pauses
                duration = random.uniform(5, 20)
            else:
                # Brief pauses
                duration = random.uniform(2, 10)

            return True, duration

        return False, 0.0


class StealthHub:
    """Central hub for browser stealth and anti-detection injection.

    All methods are ``@staticmethod`` -- no instance state is required.
    The hub aggregates:

    * **Stealth JS** -- fingerprint evasion for canvas, WebGL, audio,
      navigator, screen, timezone, Intl, and many more browser APIs.
    * **Viewport / screen dimensions** -- realistic, weighted random
      resolutions drawn from Steam/StatCounter data.
    * **User-Agent pool** -- 2025-2026 Chrome/Firefox/Edge/Safari
      strings, weighted towards Chrome market share.
    * **Pre-navigation warmup** -- organic scroll + mouse-move events
      that build a behavioural baseline before claim actions.
    * **Geo-consistency helpers** -- locale/timezone/platform
      mappings that prevent mismatch-based detection.
    """

    @staticmethod
    def get_stealth_script(
        canvas_seed: int = 12345,
        gpu_index: int = 0,
        audio_seed: int = 98765,
        languages: Optional[List[str]] = None,
        platform: str = "Win32",
        hardware_concurrency: Optional[int] = None,
    ) -> str:
        """Return a comprehensive JS stealth snippet.

        Includes v4.0 stealth protections:

        - Automation artifact deep-clean v2
          (Playwright/Selenium/Puppeteer/CDP/Camoufox)
        - Canvas/WebGL/Audio fingerprint evasion (seeded per-profile)
        - ClientRects noise, Performance timing jitter
        - Navigator property spoofing (plugins, battery, connection)
        - UserAgentData / Client Hints API consistency
        - Screen/Display consistency, Visibility/Focus fix
        - CSS media query detection evasion
        - Proxy/VPN header leak prevention
        - WebGPU fingerprint protection
        - Storage API fingerprinting protection
        - Intl API timezone/locale consistency
        - Performance.memory spoofing
        - ReportingObserver/SharedArrayBuffer protection
        - Speech synthesis voices, Clipboard protection
        - MathML rendering fingerprint protection

        Args:
            canvas_seed: Deterministic seed for canvas noise
                (ensures same profile = same fingerprint).
            gpu_index: Index into GPU configurations array
                (0-16, selected per profile).
            audio_seed: Deterministic seed for audio fingerprint
                noise.
            languages: Language list
                (e.g. ``['en-US', 'en']``).
            platform: Navigator platform string.
            hardware_concurrency: CPU core count to report
                (auto-calculated from seed if ``None``).

        Returns:
            Combined stealth script with per-profile fingerprint
            consistency.
        """
        # Lazy import: stealth_scripts is ~100 K of JS payloads
        from .stealth_scripts import (  # noqa: E402
            get_full_stealth_script,
        )
        return get_full_stealth_script(
            canvas_seed=canvas_seed,
            gpu_index=gpu_index,
            audio_seed=audio_seed,
            languages=languages,
            platform=platform,
            hardware_concurrency=hardware_concurrency,
        )

    @staticmethod
    def get_random_dimensions() -> Dict[str, Any]:
        """Return a randomised viewport and screen resolution.

        Includes the most common desktop resolutions from 2024-2026
        Steam / StatCounter data.  Weighted towards popular sizes to
        reduce fingerprint uniqueness.

        Returns:
            Dict with ``width``, ``height``, and nested ``screen``
            dict.
        """
        resolutions = [
            # Most common (1080p)
            {
                "width": 1920, "height": 1080,
                "screen": {"width": 1920, "height": 1080},
            },
            # 1440p growing
            {
                "width": 2560, "height": 1440,
                "screen": {"width": 2560, "height": 1440},
            },
            # Laptops
            {
                "width": 1366, "height": 768,
                "screen": {"width": 1366, "height": 768},
            },
            # MacBook
            {
                "width": 1440, "height": 900,
                "screen": {"width": 1440, "height": 900},
            },
            # Scaled
            {
                "width": 1536, "height": 864,
                "screen": {"width": 1536, "height": 864},
            },
            # Laptops
            {
                "width": 1600, "height": 900,
                "screen": {"width": 1600, "height": 900},
            },
            # HD
            {
                "width": 1280, "height": 720,
                "screen": {"width": 1280, "height": 720},
            },
            # 16:10
            {
                "width": 1680, "height": 1050,
                "screen": {"width": 1680, "height": 1050},
            },
            # 16:10
            {
                "width": 1920, "height": 1200,
                "screen": {"width": 1920, "height": 1200},
            },
        ]
        # Weight towards common resolutions
        weights = [35, 15, 12, 10, 8, 7, 5, 4, 4]
        return random.choices(
            resolutions, weights=weights, k=1,
        )[0]

    @staticmethod
    def get_human_ua(
        pool: Optional[List[str]] = None,
    ) -> str:
        """Return a modern, common User-Agent string.

        Updated to 2025-2026 browser versions.  Weighted towards
        Chrome (~65 % market share) to avoid statistical anomalies.

        Args:
            pool: Optional custom UA pool to draw from.

        Returns:
            A User-Agent string.
        """
        if pool:
            return random.choice(pool)

        # 2025-2026 User Agents - kept current to avoid detection
        _W = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
        )
        _M = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
        )
        _L = (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
        )

        uas = [
            # Chrome 131-134 (Windows) - most common
            _W + "Chrome/134.0.0.0 Safari/537.36",
            _W + "Chrome/133.0.0.0 Safari/537.36",
            _W + "Chrome/132.0.0.0 Safari/537.36",
            _W + "Chrome/131.0.0.0 Safari/537.36",
            # Chrome (macOS)
            _M + "Chrome/134.0.0.0 Safari/537.36",
            _M + "Chrome/133.0.0.0 Safari/537.36",
            # Chrome (Linux)
            _L + "Chrome/134.0.0.0 Safari/537.36",
            _L + "Chrome/133.0.0.0 Safari/537.36",
            # Firefox 133-135
            (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64;"
                " rv:135.0) Gecko/20100101 Firefox/135.0"
            ),
            (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64;"
                " rv:134.0) Gecko/20100101 Firefox/134.0"
            ),
            (
                "Mozilla/5.0 (X11; Linux x86_64; rv:135.0)"
                " Gecko/20100101 Firefox/135.0"
            ),
            # Edge
            (
                _W + "Chrome/134.0.0.0 Safari/537.36"
                " Edg/134.0.0.0"
            ),
            (
                _W + "Chrome/133.0.0.0 Safari/537.36"
                " Edg/133.0.0.0"
            ),
            # Safari (macOS)
            (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
                " AppleWebKit/605.1.15 (KHTML, like Gecko)"
                " Version/18.3 Safari/605.1.15"
            ),
            (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
                " AppleWebKit/605.1.15 (KHTML, like Gecko)"
                " Version/18.2 Safari/605.1.15"
            ),
        ]
        # Chrome Win > Chrome Mac > Firefox > Edge > Safari
        weights = [
            15, 12, 10, 8,   # Chrome Windows
            8, 6,             # Chrome macOS
            5, 4,             # Chrome Linux
            7, 5, 3,          # Firefox
            5, 4,             # Edge
            4, 4,             # Safari
        ]
        return random.choices(uas, weights=weights, k=1)[0]

    @staticmethod
    def get_pre_navigation_warmup_script() -> str:
        """Return JS that simulates organic page engagement.

        Should be run after page load but before any claim/action
        to look natural.  Creates scroll events, mouse movements,
        and focus/blur to build a behavioural baseline.

        Returns:
            JavaScript source string (async IIFE).
        """
        return """
        (async function() {
            'use strict';

            // Simulate initial scroll behavior
            const scrollSteps = 2 + Math.floor(Math.random() * 3);
            for (let i = 0; i < scrollSteps; i++) {
                const scrollAmount = (
                    50 + Math.floor(Math.random() * 200)
                );
                window.scrollBy({
                    top: scrollAmount, behavior: 'smooth'
                });
                await new Promise(
                    r => setTimeout(r, 300 + Math.random() * 700)
                );
            }

            // Scroll back up partially (natural reading pattern)
            const scrollBack = -(
                100 + Math.floor(Math.random() * 150)
            );
            window.scrollBy({
                top: scrollBack, behavior: 'smooth'
            });
            await new Promise(
                r => setTimeout(r, 200 + Math.random() * 500)
            );

            // Generate mouse movement events at natural positions
            const vw = window.innerWidth;
            const vh = window.innerHeight;
            const moveCount = 3 + Math.floor(Math.random() * 4);
            for (let i = 0; i < moveCount; i++) {
                const x = 100 + Math.floor(
                    Math.random() * (vw - 200)
                );
                const y = 100 + Math.floor(
                    Math.random() * (vh - 200)
                );
                const evt = new MouseEvent('mousemove', {
                    clientX: x, clientY: y,
                    bubbles: true, cancelable: true
                });
                document.dispatchEvent(evt);
                await new Promise(
                    r => setTimeout(r, 100 + Math.random() * 400)
                );
            }
        })();
        """

    @staticmethod
    def get_timezone_locale_map() -> Dict[str, List[str]]:
        """Return a map of locale to compatible timezones.

        When a proxy is in a specific region, the locale and timezone
        must match to avoid detection by timezone/locale mismatch
        checks.

        Returns:
            Dict mapping BCP-47 locale to list of IANA timezones.
        """
        return {
            "en-US": [
                "America/New_York",
                "America/Chicago",
                "America/Denver",
                "America/Los_Angeles",
                "America/Anchorage",
                "Pacific/Honolulu",
                "America/Phoenix",
                "America/Detroit",
                "America/Indiana/Indianapolis",
            ],
            "en-GB": ["Europe/London"],
            "en-CA": [
                "America/Toronto",
                "America/Vancouver",
                "America/Edmonton",
                "America/Winnipeg",
                "America/Halifax",
            ],
            "en-AU": [
                "Australia/Sydney",
                "Australia/Melbourne",
                "Australia/Brisbane",
                "Australia/Perth",
                "Australia/Adelaide",
            ],
            "de-DE": ["Europe/Berlin"],
            "fr-FR": ["Europe/Paris"],
            "ja-JP": ["Asia/Tokyo"],
            "ko-KR": ["Asia/Seoul"],
            "zh-CN": ["Asia/Shanghai"],
            "pt-BR": ["America/Sao_Paulo"],
            "es-ES": ["Europe/Madrid"],
            "it-IT": ["Europe/Rome"],
            "nl-NL": ["Europe/Amsterdam"],
            "ru-RU": ["Europe/Moscow"],
            "tr-TR": ["Europe/Istanbul"],
            "pl-PL": ["Europe/Warsaw"],
            "sv-SE": ["Europe/Stockholm"],
        }

    @staticmethod
    def get_consistent_locale_timezone(locale: str) -> str:
        """Return a geographically consistent timezone for *locale*.

        Prevents timezone/locale mismatch detection.

        Args:
            locale: BCP-47 locale string (e.g. ``en-US``).

        Returns:
            An IANA timezone string.
        """
        tz_map = StealthHub.get_timezone_locale_map()
        timezones = tz_map.get(locale, ["America/New_York"])
        return random.choice(timezones)

    @staticmethod
    def get_consistent_platform_for_ua(ua: str) -> str:
        """Return the ``navigator.platform`` matching a User-Agent.

        Prevents UA / platform mismatch detection.

        Args:
            ua: User-Agent string.

        Returns:
            Platform string (e.g. ``Win32``).
        """
        if "Windows" in ua:
            return "Win32"
        if "Macintosh" in ua or "Mac OS X" in ua:
            return "MacIntel"
        if "Linux" in ua or "X11" in ua:
            return "Linux x86_64"
        return "Win32"  # Safe default
