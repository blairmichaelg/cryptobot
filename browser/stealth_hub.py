import random
import json
import logging
from typing import Dict, Any, List

# Import fake-useragent for dynamic UA generation
try:
    from fake_useragent import UserAgent
    HAS_FAKE_UA = True
except ImportError:
    HAS_FAKE_UA = False
    logger = logging.getLogger(__name__)
    logger.warning("fake-useragent not installed. Using static list. Install with: pip install fake-useragent")

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
    def get_stealth_script(canvas_seed: int = 12345, gpu_index: int = 0) -> str:
        """
        Returns a comprehensive JavaScript snippet to be injected into the browser context.
        
        Args:
            canvas_seed: Deterministic seed for canvas noise (ensures same profile = same fingerprint)
            gpu_index: Index into GPU configurations array (0-12, selected per profile)
        
        Returns:
            Combined stealth script with per-profile fingerprint consistency
        """
        # Import here to get the latest version with fingerprint parameters
        from .stealth_scripts import get_full_stealth_script
        return get_full_stealth_script(canvas_seed=canvas_seed, gpu_index=gpu_index)

    @staticmethod
    def get_random_dimensions():
        """Returns a randomized viewport and screen resolution."""
        resolutions = [
            {"width": 1920, "height": 1080, "screen": {"width": 1920, "height": 1080}},
            {"width": 1366, "height": 768, "screen": {"width": 1366, "height": 768}},
            {"width": 1440, "height": 900, "screen": {"width": 1440, "height": 900}},
            {"width": 1536, "height": 864, "screen": {"width": 1536, "height": 864}}
        ]
        return random.choice(resolutions)

    @staticmethod
    def get_human_ua(pool: List[str] = None) -> str:
        """Returns a modern, common User Agent from a provided pool or fallback."""
        if pool:
            return random.choice(pool)
            
        uas = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 OPR/107.0.0.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15"
        ]
        return random.choice(uas)
