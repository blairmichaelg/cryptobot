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
