import random
import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class StealthHub:
    """
    Central hub for managing advanced browser stealth and anti-detection scripts.
    Goes beyond simple user-agent spoofing by handling canvas, WebGL, 
    audio fingerprinting, and navigator property protection.
    """
    
    @staticmethod
    def get_stealth_script() -> str:
        """
        Returns a comprehensive JavaScript snippet to be injected into the browser context.
        """
        # Note: This is a highly condensed version of common evasion techniques.
        # In a real production scenario, this would be even more sophisticated.
        return """
        (() => {
            // 1. Navigator Spoofing
            const maskNavigator = (navigator) => {
                const platforms = ['Win32', 'MacIntel', 'Linux x86_64'];
                const memories = [4, 8, 16, 32];
                const cores = [4, 8, 12, 16];
                
                const props = {
                    webdriver: false,
                    languages: ['en-US', 'en'],
                    platform: platforms[Math.floor(Math.random() * platforms.length)],
                    deviceMemory: memories[Math.floor(Math.random() * memories.length)],
                    hardwareConcurrency: cores[Math.floor(Math.random() * cores.length)],
                    maxTouchPoints: 0
                };
                
                for (const [key, value] of Object.entries(props)) {
                    Object.defineProperty(navigator, key, { get: () => value });
                }
            };
            maskNavigator(window.navigator);

            // 2. Canvas Fingerprint Protection (Add slight noise)
            const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
            HTMLCanvasElement.prototype.toDataURL = function(type) {
                // If the site is trying to fingerprint, we can add subtle noise here
                // For now, we just return the original but could manipulate pixels
                return originalToDataURL.apply(this, arguments);
            };

            // 3. WebGL Evasion
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                // Return common discrete GPU values instead of 'SwiftShader' or 'Headless'
                if (parameter === 37445) return 'Google Inc. (NVIDIA)';
                if (parameter === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Direct3D11 vs_5_0 ps_5_0, D3D11)';
                return getParameter.apply(this, arguments);
            };

            // 4. Audio Evasion
            const originalGetChannelData = AudioBuffer.prototype.getChannelData;
            AudioBuffer.prototype.getChannelData = function() {
                const results = originalGetChannelData.apply(this, arguments);
                // Subtle noise injection to kill deterministic audio fingerprinting
                for (let i = 0; i < 10; i++) {
                    results[i] += (Math.random() - 0.5) * 1e-7;
                }
                return results;
            };

            // 5. Hide Playwright/Puppeteer Indicators
            delete window.cdc_adoQtmxX7f7o86DBjCWfW_Array;
            delete window.cdc_adoQtmxX7f7o86DBjCWfW_Promise;
            delete window.cdc_adoQtmxX7f7o86DBjCWfW_Symbol;
        })();
        """

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
