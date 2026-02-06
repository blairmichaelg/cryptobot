import random
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

class HumanProfile:
    """
    Human behavioral timing profiles for stealth automation.
    Each profile simulates distinct user behavior patterns.
    """
    FAST_USER = "fast"          # 0.5-2s delays, occasional bursts
    NORMAL_USER = "normal"      # 2-5s delays, steady pace  
    CAUTIOUS_USER = "cautious"  # 5-15s delays, frequent pauses
    DISTRACTED_USER = "distracted"  # Random 10-60s gaps, multitasking
    
    ALL_PROFILES = [FAST_USER, NORMAL_USER, CAUTIOUS_USER, DISTRACTED_USER]
    
    # Action-specific timing ranges for each profile (min, max in seconds)
    TIMING_RANGES = {
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
        }
    }
    
    @staticmethod
    def get_random_profile() -> str:
        """Return a random profile with weighted distribution."""
        # Weight distribution: normal > cautious > fast > distracted
        weights = [15, 50, 25, 10]  # FAST, NORMAL, CAUTIOUS, DISTRACTED
        return random.choices(HumanProfile.ALL_PROFILES, weights=weights, k=1)[0]
    
    @staticmethod
    def get_action_delay(profile: str, action_type: str = "click") -> float:
        """
        Get delay for specific action type based on profile.
        
        Args:
            profile: User profile type (fast/normal/cautious/distracted)
            action_type: Action type (click/type/scroll/read)
            
        Returns:
            Delay in seconds
        """
        if profile not in HumanProfile.TIMING_RANGES:
            profile = HumanProfile.NORMAL_USER
            
        if action_type not in HumanProfile.TIMING_RANGES[profile]:
            action_type = "click"
            
        min_delay, max_delay = HumanProfile.TIMING_RANGES[profile][action_type]
        
        # Add profile-specific variance
        if profile == HumanProfile.FAST_USER:
            # 20% chance of burst mode (very fast)
            if random.random() < 0.20:
                return random.uniform(0.1, 0.3)
        elif profile == HumanProfile.CAUTIOUS_USER:
            # Occasional extra-long pauses (10% chance)
            if random.random() < 0.10:
                return random.uniform(max_delay, max_delay * 2)
        
        return random.uniform(min_delay, max_delay)
    
    @staticmethod
    def get_thinking_pause(profile: str) -> float:
        """
        Get realistic "thinking" pause before important actions.
        
        Args:
            profile: User profile type
            
        Returns:
            Delay in seconds
        """
        return HumanProfile.get_action_delay(profile, "thinking")
    
    @staticmethod
    def should_idle(profile: str) -> tuple[bool, float]:
        """
        Determine if user should pause (simulates distraction).
        
        Args:
            profile: User profile type
            
        Returns:
            Tuple of (should_pause: bool, pause_duration: float)
        """
        idle_probabilities = {
            HumanProfile.FAST_USER: 0.05,       # 5% chance
            HumanProfile.NORMAL_USER: 0.10,     # 10% chance
            HumanProfile.CAUTIOUS_USER: 0.15,   # 15% chance
            HumanProfile.DISTRACTED_USER: 0.30, # 30% chance
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
    """
    Central hub for managing advanced browser stealth and anti-detection scripts.
    Goes beyond simple user-agent spoofing by handling canvas, WebGL, 
    audio fingerprinting, and navigator property protection.
    """
    
    @staticmethod
    def get_stealth_script(canvas_seed: int = 12345, gpu_index: int = 0, audio_seed: int = 98765, languages: Optional[List[str]] = None, platform: str = "Win32", hardware_concurrency: Optional[int] = None) -> str:
        """
        Returns a comprehensive JavaScript snippet to be injected into the browser context.
        
        Includes v3.0 stealth protections:
        - Automation artifact deep-clean (Playwright/Selenium/Puppeteer/CDP)
        - Canvas/WebGL/Audio fingerprint evasion (seeded per-profile)
        - ClientRects noise, Performance timing jitter
        - Navigator property spoofing (plugins, battery, connection, devices)
        - Screen/Display consistency, Visibility/Focus fix
        - Proxy/VPN header leak prevention
        - Speech synthesis voices, Clipboard protection
        
        Args:
            canvas_seed: Deterministic seed for canvas noise (ensures same profile = same fingerprint)
            gpu_index: Index into GPU configurations array (0-16, selected per profile)
            audio_seed: Deterministic seed for audio fingerprint noise
            languages: Language list (e.g., ['en-US', 'en'])
            platform: Navigator platform string
            hardware_concurrency: CPU core count to report (auto-calculated from seed if None)
        
        Returns:
            Combined stealth script with per-profile fingerprint consistency
        """
        from .stealth_scripts import get_full_stealth_script
        return get_full_stealth_script(
            canvas_seed=canvas_seed,
            gpu_index=gpu_index,
            audio_seed=audio_seed,
            languages=languages,
            platform=platform,
            hardware_concurrency=hardware_concurrency
        )

    @staticmethod
    def get_random_dimensions():
        """Returns a randomized viewport and screen resolution.
        
        Includes the most common desktop resolutions from 2024-2026 Steam/StatCounter data.
        Weighted towards most popular to reduce fingerprint uniqueness.
        """
        resolutions = [
            {"width": 1920, "height": 1080, "screen": {"width": 1920, "height": 1080}},  # Most common
            {"width": 2560, "height": 1440, "screen": {"width": 2560, "height": 1440}},  # 1440p growing
            {"width": 1366, "height": 768, "screen": {"width": 1366, "height": 768}},   # Laptops
            {"width": 1440, "height": 900, "screen": {"width": 1440, "height": 900}},   # MacBook
            {"width": 1536, "height": 864, "screen": {"width": 1536, "height": 864}},   # Scaled
            {"width": 1600, "height": 900, "screen": {"width": 1600, "height": 900}},   # Laptops
            {"width": 1280, "height": 720, "screen": {"width": 1280, "height": 720}},   # HD
            {"width": 1680, "height": 1050, "screen": {"width": 1680, "height": 1050}}, # 16:10
            {"width": 1920, "height": 1200, "screen": {"width": 1920, "height": 1200}}, # 16:10
        ]
        # Weight towards common resolutions
        weights = [35, 15, 12, 10, 8, 7, 5, 4, 4]
        return random.choices(resolutions, weights=weights, k=1)[0]

    @staticmethod
    def get_human_ua(pool: Optional[List[str]] = None) -> str:
        """Returns a modern, common User Agent from a provided pool or fallback.
        
        Updated to 2025-2026 browser versions. Weighted towards Chrome (65% market share)
        to avoid statistical anomalies.
        """
        if pool:
            return random.choice(pool)
        
        # 2025-2026 User Agents - kept current to avoid old-version detection
        uas = [
            # Chrome 131-134 (Windows) - most common
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            # Chrome (macOS)
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            # Chrome (Linux)
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            # Firefox 133-135
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:134.0) Gecko/20100101 Firefox/134.0",
            "Mozilla/5.0 (X11; Linux x86_64; rv:135.0) Gecko/20100101 Firefox/135.0",
            # Edge
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 Edg/134.0.0.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0",
            # Safari (macOS)
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Safari/605.1.15",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
        ]
        # Weight: Chrome Windows > Chrome Mac > Firefox > Edge > Safari > Chrome Linux
        weights = [15, 12, 10, 8, 8, 6, 5, 4, 7, 5, 3, 5, 4, 4, 4]
        return random.choices(uas, weights=weights, k=1)[0]
