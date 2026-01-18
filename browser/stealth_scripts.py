"""
Centralized browser stealth/anti-fingerprinting scripts.

These scripts are injected into browser contexts to prevent fingerprinting
and detection by anti-bot systems. Based on research of modern anti-detection
techniques used in 2024-2025.
"""

# WebRTC Leak Prevention - Prevents IP leak through STUN/TURN servers
WEBRTC_PROTECTION = """
(function() {
    // Disable navigator.webdriver flag
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
        configurable: true
    });
    
    // Neutralize RTCPeerConnection to prevent WebRTC IP leaks
    if (window.RTCPeerConnection) {
        const originalRTC = window.RTCPeerConnection;
        window.RTCPeerConnection = function(config) {
            if (config && config.iceServers) {
                config.iceServers = []; // Remove TURN/STUN servers
            }
            return new originalRTC(config);
        };
        window.RTCPeerConnection.prototype = originalRTC.prototype;
    }
    
    // Also handle webkit prefix
    if (window.webkitRTCPeerConnection) {
        const originalWebkitRTC = window.webkitRTCPeerConnection;
        window.webkitRTCPeerConnection = function(config) {
            if (config && config.iceServers) {
                config.iceServers = [];
            }
            return new originalWebkitRTC(config);
        };
    }
})();
"""

# Canvas Fingerprint Evasion - Adds noise to canvas rendering
CANVAS_EVASION = """
(function() {
    // Store original methods
    const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
    const originalGetImageData = CanvasRenderingContext2D.prototype.getImageData;
    
    // Subtle noise injection for toDataURL
    HTMLCanvasElement.prototype.toDataURL = function(type) {
        const ctx = this.getContext('2d');
        if (ctx && this.width > 0 && this.height > 0) {
            try {
                // Add imperceptible noise
                const imageData = ctx.getImageData(0, 0, Math.min(this.width, 10), Math.min(this.height, 10));
                const data = imageData.data;
                for (let i = 0; i < data.length; i += 4) {
                    // Very subtle color shifts (unnoticeable to human eye)
                    data[i] = Math.max(0, Math.min(255, data[i] + (Math.random() - 0.5) * 2));
                }
                ctx.putImageData(imageData, 0, 0);
            } catch(e) {
                // Canvas may be tainted, ignore
            }
        }
        return originalToDataURL.apply(this, arguments);
    };
    
    // Add noise to getImageData as well
    CanvasRenderingContext2D.prototype.getImageData = function(sx, sy, sw, sh) {
        const imageData = originalGetImageData.apply(this, arguments);
        const data = imageData.data;
        for (let i = 0; i < data.length; i += 4) {
            data[i] = Math.max(0, Math.min(255, data[i] + (Math.random() - 0.5) * 2));
        }
        return imageData;
    };
})();
"""

# WebGL Fingerprint Evasion - Randomizes WebGL renderer/vendor info
WEBGL_EVASION = """
(function() {
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    
    // Randomized but realistic-looking values
    const spoofedData = {
        37445: 'Intel Inc.',  // UNMASKED_VENDOR_WEBGL
        37446: 'Intel(R) UHD Graphics 620',  // UNMASKED_RENDERER_WEBGL
    };
    
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (spoofedData[parameter]) {
            return spoofedData[parameter];
        }
        return getParameter.apply(this, arguments);
    };
    
    // Apply to WebGL2 as well
    if (window.WebGL2RenderingContext) {
        const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
        WebGL2RenderingContext.prototype.getParameter = function(parameter) {
            if (spoofedData[parameter]) {
                return spoofedData[parameter];
            }
            return getParameter2.apply(this, arguments);
        };
    }
})();
"""

# Audio Fingerprint Prevention - Adds noise to AudioContext
AUDIO_EVASION = """
(function() {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;
    
    const originalGetChannelData = AudioBuffer.prototype.getChannelData;
    
    AudioBuffer.prototype.getChannelData = function(channel) {
        const data = originalGetChannelData.apply(this, arguments);
        // Add imperceptible noise
        for (let i = 0; i < data.length; i += 100) {
            data[i] = data[i] + (Math.random() - 0.5) * 0.0001;
        }
        return data;
    };
    
    // Also randomize sample rate slightly in the reported value
    const origCreateOscillator = AudioContext.prototype.createOscillator;
    AudioContext.prototype.createOscillator = function() {
        const osc = origCreateOscillator.apply(this, arguments);
        // Small frequency offset
        const origFreq = osc.frequency.value;
        osc.frequency.value = origFreq + (Math.random() - 0.5) * 0.001;
        return osc;
    };
})();
"""

# Navigator Property Spoofing - Hides automation indicators
NAVIGATOR_SPOOF = """
(function() {
    // Hide automation indicators
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
        configurable: true
    });
    
    // Spoof plugins array (empty arrays are suspicious)
    const fakePlugins = {
        length: 3,
        0: { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
        1: { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
        2: { name: 'Native Client', filename: 'internal-nacl-plugin' },
        item: function(i) { return this[i]; },
        namedItem: function(name) { 
            for (let i = 0; i < this.length; i++) {
                if (this[i].name === name) return this[i];
            }
            return null;
        },
        refresh: function() {}
    };
    
    try {
        Object.defineProperty(navigator, 'plugins', {
            get: () => fakePlugins,
            configurable: true
        });
    } catch(e) {}
    
    // Spoof languages
    try {
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
            configurable: true
        });
    } catch(e) {}
    
    // Hide Chrome automation flags
    if (window.chrome) {
        window.chrome.runtime = undefined;
    }
    
    // Override permissions query for notifications
    const originalQuery = Permissions.prototype.query;
    Permissions.prototype.query = function(parameters) {
        if (parameters.name === 'notifications') {
            return Promise.resolve({ state: Notification.permission });
        }
        return originalQuery.apply(this, arguments);
    };
})();
"""

# Font Fingerprint Mitigation - Limits exposed fonts
FONT_PROTECTION = """
(function() {
    // Override font checking to return consistent results
    const originalOffsetWidth = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetWidth');
    const originalOffsetHeight = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetHeight');
    
    // Common fonts that should always appear "installed"
    const baseFonts = ['monospace', 'sans-serif', 'serif'];
    const commonFonts = ['Arial', 'Times New Roman', 'Courier New', 'Georgia', 'Verdana'];
    
    // Add slight randomization to measurements
    if (originalOffsetWidth && originalOffsetWidth.get) {
        Object.defineProperty(HTMLElement.prototype, 'offsetWidth', {
            get: function() {
                const width = originalOffsetWidth.get.call(this);
                // Only add noise for hidden font-detection elements
                if (this.style.visibility === 'hidden' || this.style.position === 'absolute') {
                    return width + (Math.random() < 0.1 ? 1 : 0);
                }
                return width;
            }
        });
    }
})();
"""


def get_full_stealth_script() -> str:
    """
    Return combined stealth script for browser initialization.
    
    This script should be injected via context.add_init_script()
    to run before any page scripts execute.
    
    Returns:
        Combined JavaScript string containing all evasion techniques.
    """
    return "\n\n".join([
        "// === STEALTH SCRIPTS START ===",
        WEBRTC_PROTECTION,
        CANVAS_EVASION,
        WEBGL_EVASION,
        AUDIO_EVASION,
        NAVIGATOR_SPOOF,
        FONT_PROTECTION,
        "// === STEALTH SCRIPTS END ==="
    ])


def get_minimal_stealth_script() -> str:
    """
    Return a minimal stealth script for lightweight contexts.
    
    Use this when full stealth is not needed or performance is critical.
    """
    return "\n\n".join([
        WEBRTC_PROTECTION,
        NAVIGATOR_SPOOF
    ])
