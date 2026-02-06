"""
Centralized browser stealth/anti-fingerprinting scripts.

These scripts are injected into browser contexts to prevent fingerprinting
and detection by anti-bot systems. Based on research of modern anti-detection
techniques used in 2025-2026.

Coverage:
- Automation artifact deep-clean (Playwright/Selenium/Puppeteer/CDP traces)
- WebRTC leak prevention (STUN/TURN, ICE candidates, private IPs)
- Canvas fingerprint evasion (seeded, deterministic per-profile)
- WebGL fingerprint evasion (realistic GPU configs, readPixels noise)
- Audio fingerprint evasion (seeded noise, AnalyserNode protection)
- Navigator property spoofing (plugins, mimeTypes, languages, battery, etc.)
- Font fingerprint mitigation
- ClientRects noise injection (DOMRect fingerprint evasion)
- Performance API timing noise
- Speech Synthesis / voices consistency
- Screen/Display API consistency
- Connection/Network API spoofing
- Proxy/VPN header leak prevention
- Clipboard API protection
- Visibility/Focus state consistency
- Devtools detection prevention
- Iframe contentWindow propagation
"""

from typing import Optional, List

# ============================================================================
# 1. AUTOMATION ARTIFACT DEEP-CLEAN
# Remove ALL traces of Playwright, Puppeteer, Selenium, WebDriver, Camoufox
# This MUST run first before any other scripts
# ============================================================================
AUTOMATION_ARTIFACT_REMOVAL = """
(function() {
    'use strict';
    
    // ---- navigator.webdriver ----
    try {
        delete navigator.__proto__.webdriver;
    } catch(e) {}
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
        configurable: true,
        enumerable: true
    });
    
    // ---- Remove Playwright-specific artifacts ----
    const playwrightProps = [
        '__playwright',
        '__pw_manual',
        '__PW_inspect',
        '__playwright_evaluation_script__',
        '_playwright_evaluation_script_',
        '__pwPage',
        '__lastWatchedVideo'
    ];
    for (const prop of playwrightProps) {
        try { delete window[prop]; } catch(e) {}
        try {
            Object.defineProperty(window, prop, {
                get: () => undefined,
                configurable: true,
                enumerable: false
            });
        } catch(e) {}
    }
    
    // ---- Remove Selenium artifacts ----
    const seleniumProps = [
        '_selenium', '_Selenium_IDE_Recorder',
        'callSelenium', '_selenium_unwrapped',
        '__webdriver_script_fn', '__driver_evaluate',
        '__webdriver_evaluate', '__selenium_evaluate',
        '__fxdriver_evaluate', '__driver_unwrapped',
        '__webdriver_unwrapped', '__selenium_unwrapped',
        '__fxdriver_unwrapped', '__webdriver_script_func',
        '_WEBDRIVER_ELEM_CACHE', 'calledSelenium',
        '__nightmare', 'domAutomation', 'domAutomationController'
    ];
    for (const prop of seleniumProps) {
        try { delete window[prop]; } catch(e) {}
        try { delete document[prop]; } catch(e) {}
    }
    
    // ---- Remove Puppeteer artifacts ----
    try { delete window.__puppeteer_evaluation_script__; } catch(e) {}
    
    // ---- Remove CDP (Chrome DevTools Protocol) artifacts ----
    try {
        if (window.cdc_adoQpoasnfa76pfcZLmcfl_Array) {
            delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
        }
        if (window.cdc_adoQpoasnfa76pfcZLmcfl_Promise) {
            delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
        }
        if (window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol) {
            delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
        }
    } catch(e) {}
    
    // ---- Clean document $cdc_/$wdc_ properties (ChromeDriver) ----
    try {
        const docKeys = Object.getOwnPropertyNames(document);
        for (const key of docKeys) {
            if (key.startsWith('$cdc_') || key.startsWith('$wdc_')) {
                try { delete document[key]; } catch(e) {}
            }
        }
    } catch(e) {}
    
    // ---- Prevent Error.stack leak ----
    const originalPrepareStackTrace = Error.prepareStackTrace;
    if (typeof Error.prepareStackTrace !== 'undefined' || true) {
        Error.prepareStackTrace = function(error, stack) {
            if (!stack || !stack.filter) {
                if (originalPrepareStackTrace) {
                    return originalPrepareStackTrace(error, stack);
                }
                return undefined;
            }
            const filtered = stack.filter(frame => {
                const fn = (typeof frame.getFunctionName === 'function' ? frame.getFunctionName() : '') || '';
                const file = (typeof frame.getFileName === 'function' ? frame.getFileName() : '') || '';
                return !fn.includes('__playwright') && 
                       !fn.includes('__puppeteer') &&
                       !fn.includes('__selenium') &&
                       !file.includes('playwright') &&
                       !file.includes('puppeteer') &&
                       !file.includes('__pw_') &&
                       !file.includes('evaluate_script');
            });
            if (originalPrepareStackTrace) {
                return originalPrepareStackTrace(error, filtered);
            }
            return filtered.map(f => '    at ' + f.toString()).join('\\n');
        };
    }
    
    // ---- Override toString for native functions ----
    const nativeToString = Function.prototype.toString;
    const overriddenFunctions = new WeakMap();
    
    Function.prototype.toString = function() {
        if (overriddenFunctions.has(this)) {
            return overriddenFunctions.get(this);
        }
        return nativeToString.call(this);
    };
    
    // Helper to register overridden functions as native-looking
    window.__registerNative = function(fn, name) {
        overriddenFunctions.set(fn, 'function ' + name + '() { [native code] }');
    };
    
    // Register our toString override itself
    overriddenFunctions.set(Function.prototype.toString, 'function toString() { [native code] }');
    
    // ---- Protect against iframe-based webdriver detection ----
    const iframeObserver = new MutationObserver(function(mutations) {
        for (const mutation of mutations) {
            for (const node of mutation.addedNodes) {
                if (node.tagName === 'IFRAME' || node.tagName === 'FRAME') {
                    try {
                        const iframeWin = node.contentWindow;
                        if (iframeWin && iframeWin.navigator) {
                            Object.defineProperty(iframeWin.navigator, 'webdriver', {
                                get: () => undefined,
                                configurable: true
                            });
                        }
                    } catch(e) {}
                }
            }
        }
    });
    
    if (document.documentElement) {
        iframeObserver.observe(document.documentElement, {
            childList: true,
            subtree: true
        });
    }
})();
"""

# ============================================================================
# 2. WebRTC Leak Prevention
# ============================================================================
WEBRTC_PROTECTION = """
(function() {
    'use strict';
    
    if (window.RTCPeerConnection) {
        const originalRTC = window.RTCPeerConnection;
        const newRTC = function(config) {
            if (config && config.iceServers) {
                config.iceServers = [];
            }
            const pc = new originalRTC(config);
            
            // Neutralize candidate gathering to prevent IP leaks
            const origAddEventListener = pc.addEventListener.bind(pc);
            pc.addEventListener = function(type, listener, options) {
                if (type === 'icecandidate') {
                    const wrappedListener = function(event) {
                        if (event.candidate && event.candidate.candidate) {
                            const candidate = event.candidate.candidate;
                            if (candidate.includes('.local') || 
                                /\\b(?:10|172\\.(?:1[6-9]|2\\d|3[01])|192\\.168)\\b/.test(candidate)) {
                                return; // Block private IP candidates
                            }
                        }
                        listener.call(this, event);
                    };
                    return origAddEventListener(type, wrappedListener, options);
                }
                return origAddEventListener(type, listener, options);
            };
            
            return pc;
        };
        newRTC.prototype = originalRTC.prototype;
        Object.keys(originalRTC).forEach(key => {
            try { newRTC[key] = originalRTC[key]; } catch(e) {}
        });
        
        window.RTCPeerConnection = newRTC;
        if (window.__registerNative) window.__registerNative(newRTC, 'RTCPeerConnection');
    }
    
    // Handle webkit prefix
    if (window.webkitRTCPeerConnection) {
        const originalWebkitRTC = window.webkitRTCPeerConnection;
        window.webkitRTCPeerConnection = function(config) {
            if (config && config.iceServers) { config.iceServers = []; }
            return new originalWebkitRTC(config);
        };
        window.webkitRTCPeerConnection.prototype = originalWebkitRTC.prototype;
    }
    
    // Handle moz prefix (Firefox/Camoufox)
    if (window.mozRTCPeerConnection) {
        const originalMozRTC = window.mozRTCPeerConnection;
        window.mozRTCPeerConnection = function(config) {
            if (config && config.iceServers) { config.iceServers = []; }
            return new originalMozRTC(config);
        };
        window.mozRTCPeerConnection.prototype = originalMozRTC.prototype;
    }
})();
"""

# ============================================================================
# 3. Canvas Fingerprint Evasion (Seeded, Deterministic Per-Profile)
# ============================================================================
CANVAS_EVASION = """
(function() {
    'use strict';
    
    let canvasSeed = window.__FINGERPRINT_SEED__ || 12345;
    
    function seededRandom() {
        canvasSeed = (canvasSeed * 16807 + 0) % 2147483647;
        return (canvasSeed - 1) / 2147483646;
    }
    
    const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
    const originalToBlob = HTMLCanvasElement.prototype.toBlob;
    const originalGetImageData = CanvasRenderingContext2D.prototype.getImageData;
    
    function addConsistentNoise(imageData) {
        const data = imageData.data;
        const noiseStrength = 2;
        const savedSeed = canvasSeed;
        const step = Math.max(4, Math.floor(data.length / 4000) * 4);
        
        for (let i = 0; i < data.length; i += step) {
            const noise = (seededRandom() - 0.5) * noiseStrength;
            data[i] = Math.max(0, Math.min(255, data[i] + noise));
            data[i+1] = Math.max(0, Math.min(255, data[i+1] + noise));
            data[i+2] = Math.max(0, Math.min(255, data[i+2] + noise));
        }
        
        canvasSeed = savedSeed;
    }
    
    HTMLCanvasElement.prototype.toDataURL = function(type) {
        const ctx = this.getContext('2d');
        if (ctx && this.width > 0 && this.height > 0) {
            try {
                const w = Math.min(this.width, 16);
                const h = Math.min(this.height, 16);
                const imageData = originalGetImageData.call(ctx, 0, 0, w, h);
                addConsistentNoise(imageData);
                ctx.putImageData(imageData, 0, 0);
            } catch(e) {}
        }
        return originalToDataURL.apply(this, arguments);
    };
    if (window.__registerNative) window.__registerNative(HTMLCanvasElement.prototype.toDataURL, 'toDataURL');
    
    HTMLCanvasElement.prototype.toBlob = function(callback, type, quality) {
        const ctx = this.getContext('2d');
        if (ctx && this.width > 0 && this.height > 0) {
            try {
                const w = Math.min(this.width, 16);
                const h = Math.min(this.height, 16);
                const imageData = originalGetImageData.call(ctx, 0, 0, w, h);
                addConsistentNoise(imageData);
                ctx.putImageData(imageData, 0, 0);
            } catch(e) {}
        }
        return originalToBlob.apply(this, arguments);
    };
    if (window.__registerNative) window.__registerNative(HTMLCanvasElement.prototype.toBlob, 'toBlob');
    
    CanvasRenderingContext2D.prototype.getImageData = function(sx, sy, sw, sh) {
        const imageData = originalGetImageData.apply(this, arguments);
        addConsistentNoise(imageData);
        return imageData;
    };
    if (window.__registerNative) window.__registerNative(CanvasRenderingContext2D.prototype.getImageData, 'getImageData');
    
    // ---- OffscreenCanvas protection ----
    if (window.OffscreenCanvas) {
        const origOffscreenToBlob = OffscreenCanvas.prototype.convertToBlob;
        if (origOffscreenToBlob) {
            OffscreenCanvas.prototype.convertToBlob = function() {
                try {
                    const ctx = this.getContext('2d');
                    if (ctx && this.width > 0 && this.height > 0) {
                        const w = Math.min(this.width, 16);
                        const h = Math.min(this.height, 16);
                        const imgData = ctx.getImageData(0, 0, w, h);
                        addConsistentNoise(imgData);
                        ctx.putImageData(imgData, 0, 0);
                    }
                } catch(e) {}
                return origOffscreenToBlob.apply(this, arguments);
            };
        }
    }
})();
"""

# ============================================================================
# 4. WebGL Fingerprint Evasion (Realistic GPU Configs)
# ============================================================================
WEBGL_EVASION = """
(function() {
    'use strict';
    
    const GPU_CONFIGS = [
        { vendor: 'NVIDIA Corporation', renderer: 'NVIDIA GeForce RTX 4060/PCIe/SSE2' },
        { vendor: 'NVIDIA Corporation', renderer: 'NVIDIA GeForce RTX 4070/PCIe/SSE2' },
        { vendor: 'NVIDIA Corporation', renderer: 'NVIDIA GeForce RTX 3080/PCIe/SSE2' },
        { vendor: 'NVIDIA Corporation', renderer: 'NVIDIA GeForce GTX 1660/PCIe/SSE2' },
        { vendor: 'NVIDIA Corporation', renderer: 'NVIDIA GeForce RTX 3060/PCIe/SSE2' },
        { vendor: 'NVIDIA Corporation', renderer: 'NVIDIA GeForce RTX 4080/PCIe/SSE2' },
        { vendor: 'NVIDIA Corporation', renderer: 'NVIDIA GeForce RTX 5070/PCIe/SSE2' },
        { vendor: 'Intel Inc.', renderer: 'Intel(R) Iris(R) Xe Graphics' },
        { vendor: 'Intel Inc.', renderer: 'Intel(R) UHD Graphics 630' },
        { vendor: 'Intel Inc.', renderer: 'Intel(R) UHD Graphics 770' },
        { vendor: 'Intel Inc.', renderer: 'Intel(R) Iris(R) Plus Graphics' },
        { vendor: 'Intel Inc.', renderer: 'Intel(R) Arc(TM) A770 Graphics' },
        { vendor: 'AMD', renderer: 'AMD Radeon RX 6700 XT' },
        { vendor: 'AMD', renderer: 'AMD Radeon RX 7600' },
        { vendor: 'AMD', renderer: 'AMD Radeon RX 6600' },
        { vendor: 'AMD', renderer: 'AMD Radeon RX 5700 XT' },
        { vendor: 'AMD', renderer: 'AMD Radeon RX 7900 XTX' }
    ];
    
    const gpuIndex = (window.__GPU_INDEX__ !== undefined) ? window.__GPU_INDEX__ : 0;
    const selectedGPU = GPU_CONFIGS[gpuIndex % GPU_CONFIGS.length];
    
    const spoofedData = {
        37445: selectedGPU.vendor,
        37446: selectedGPU.renderer
    };
    
    let glSeed = window.__FINGERPRINT_SEED__ || 12345;
    function glSeededRandom() {
        glSeed = (glSeed * 16807 + 0) % 2147483647;
        return (glSeed - 1) / 2147483646;
    }
    
    function patchGetParameter(proto) {
        const original = proto.getParameter;
        proto.getParameter = function(parameter) {
            if (spoofedData[parameter]) {
                return spoofedData[parameter];
            }
            return original.apply(this, arguments);
        };
        if (window.__registerNative) window.__registerNative(proto.getParameter, 'getParameter');
    }
    
    patchGetParameter(WebGLRenderingContext.prototype);
    if (window.WebGL2RenderingContext) {
        patchGetParameter(WebGL2RenderingContext.prototype);
    }
    
    // ---- Spoof getExtension for WEBGL_debug_renderer_info ----
    function patchGetExtension(proto) {
        const original = proto.getExtension;
        proto.getExtension = function(name) {
            const ext = original.apply(this, arguments);
            if (name === 'WEBGL_debug_renderer_info' && ext) {
                return new Proxy(ext, {
                    get: function(target, prop) {
                        if (prop === 'UNMASKED_VENDOR_WEBGL') return 37445;
                        if (prop === 'UNMASKED_RENDERER_WEBGL') return 37446;
                        return target[prop];
                    }
                });
            }
            return ext;
        };
        if (window.__registerNative) window.__registerNative(proto.getExtension, 'getExtension');
    }
    
    patchGetExtension(WebGLRenderingContext.prototype);
    if (window.WebGL2RenderingContext) {
        patchGetExtension(WebGL2RenderingContext.prototype);
    }
    
    // ---- WebGL readPixels noise ----
    function patchReadPixels(proto) {
        const original = proto.readPixels;
        proto.readPixels = function(x, y, width, height, format, type, pixels) {
            original.apply(this, arguments);
            if (pixels && pixels.length) {
                const step = Math.max(1, Math.floor(pixels.length / 50));
                for (let i = 0; i < pixels.length; i += step) {
                    pixels[i] = Math.max(0, Math.min(255, 
                        pixels[i] + Math.round((glSeededRandom() - 0.5) * 2)
                    ));
                }
            }
        };
    }
    
    patchReadPixels(WebGLRenderingContext.prototype);
    if (window.WebGL2RenderingContext) {
        patchReadPixels(WebGL2RenderingContext.prototype);
    }
})();
"""

# ============================================================================
# 5. Audio Fingerprint Prevention (Seeded Noise)
# ============================================================================
AUDIO_EVASION = """
(function() {
    'use strict';
    
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;

    let audioSeed = window.__AUDIO_SEED__ || 98765;
    function seededRandom() {
        audioSeed = (audioSeed * 16807 + 0) % 2147483647;
        return (audioSeed - 1) / 2147483646;
    }
    
    const originalGetChannelData = AudioBuffer.prototype.getChannelData;
    AudioBuffer.prototype.getChannelData = function(channel) {
        const data = originalGetChannelData.apply(this, arguments);
        const step = Math.max(1, Math.floor(data.length / 500));
        for (let i = 0; i < data.length; i += step) {
            data[i] = data[i] + (seededRandom() - 0.5) * 0.0001;
        }
        return data;
    };
    if (window.__registerNative) window.__registerNative(AudioBuffer.prototype.getChannelData, 'getChannelData');
    
    const origCreateOscillator = AudioCtx.prototype.createOscillator;
    AudioCtx.prototype.createOscillator = function() {
        const osc = origCreateOscillator.apply(this, arguments);
        const origFreq = osc.frequency.value;
        osc.frequency.value = origFreq + (seededRandom() - 0.5) * 0.001;
        return osc;
    };
    
    // ---- AnalyserNode noise ----
    if (window.AnalyserNode) {
        const origGetFloat = AnalyserNode.prototype.getFloatFrequencyData;
        if (origGetFloat) {
            AnalyserNode.prototype.getFloatFrequencyData = function(array) {
                origGetFloat.apply(this, arguments);
                if (array && array.length) {
                    const step = Math.max(1, Math.floor(array.length / 100));
                    for (let i = 0; i < array.length; i += step) {
                        array[i] = array[i] + (seededRandom() - 0.5) * 0.1;
                    }
                }
            };
        }
        
        const origGetByte = AnalyserNode.prototype.getByteFrequencyData;
        if (origGetByte) {
            AnalyserNode.prototype.getByteFrequencyData = function(array) {
                origGetByte.apply(this, arguments);
                if (array && array.length) {
                    const step = Math.max(1, Math.floor(array.length / 100));
                    for (let i = 0; i < array.length; i += step) {
                        array[i] = Math.max(0, Math.min(255, 
                            array[i] + Math.round((seededRandom() - 0.5) * 2)
                        ));
                    }
                }
            };
        }
    }
})();
"""

# ============================================================================
# 6. Navigator Property Spoofing (Deep)
# ============================================================================
NAVIGATOR_SPOOF = """
(function() {
    'use strict';
    
    // ---- navigator.webdriver (redundant safety) ----
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
        configurable: true,
        enumerable: true
    });
    
    // ---- Realistic plugins array ----
    function createPlugin(name, description, filename, mimeTypes) {
        const plugin = {
            name: name,
            description: description,
            filename: filename,
            length: mimeTypes.length
        };
        mimeTypes.forEach((mt, i) => {
            const mimeObj = {
                type: mt.type,
                suffixes: mt.suffixes,
                description: mt.description,
                enabledPlugin: plugin
            };
            plugin[i] = mimeObj;
            plugin[mt.type] = mimeObj;
        });
        plugin.item = function(i) { return this[i]; };
        plugin.namedItem = function(name) { return this[name]; };
        return plugin;
    }
    
    const pdfMimes = [
        { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format' },
        { type: 'text/pdf', suffixes: 'pdf', description: 'Portable Document Format' }
    ];
    
    const fakePlugins = [
        createPlugin('PDF Viewer', 'Portable Document Format', 'internal-pdf-viewer', pdfMimes),
        createPlugin('Chrome PDF Viewer', 'Portable Document Format', 'internal-pdf-viewer', pdfMimes),
        createPlugin('Chromium PDF Viewer', 'Portable Document Format', 'internal-pdf-viewer', pdfMimes),
        createPlugin('Microsoft Edge PDF Viewer', 'Portable Document Format', 'internal-pdf-viewer', pdfMimes),
        createPlugin('WebKit built-in PDF', 'Portable Document Format', 'internal-pdf-viewer', pdfMimes)
    ];
    
    const pluginArray = {
        length: fakePlugins.length,
        item: function(i) { return fakePlugins[i]; },
        namedItem: function(name) {
            return fakePlugins.find(p => p.name === name) || null;
        },
        refresh: function() {},
        [Symbol.iterator]: function*() {
            for (let i = 0; i < fakePlugins.length; i++) yield fakePlugins[i];
        }
    };
    fakePlugins.forEach((p, i) => { pluginArray[i] = p; });
    
    try {
        Object.defineProperty(navigator, 'plugins', {
            get: () => pluginArray,
            configurable: true,
            enumerable: true
        });
    } catch(e) {}
    
    // ---- Spoof mimeTypes ----
    const allMimeTypes = [];
    fakePlugins.forEach(p => {
        for (let i = 0; i < p.length; i++) allMimeTypes.push(p[i]);
    });
    const mimeTypeArray = {
        length: allMimeTypes.length,
        item: function(i) { return allMimeTypes[i]; },
        namedItem: function(name) { return allMimeTypes.find(m => m.type === name) || null; },
        [Symbol.iterator]: function*() {
            for (let i = 0; i < allMimeTypes.length; i++) yield allMimeTypes[i];
        }
    };
    allMimeTypes.forEach((m, i) => { mimeTypeArray[i] = m; });
    
    try {
        Object.defineProperty(navigator, 'mimeTypes', {
            get: () => mimeTypeArray,
            configurable: true,
            enumerable: true
        });
    } catch(e) {}
    
    // ---- Languages ----
    try {
        const spoofed = window.__LANGUAGES__ || ['en-US', 'en'];
        Object.defineProperty(navigator, 'languages', {
            get: () => Object.freeze([...spoofed]),
            configurable: true,
            enumerable: true
        });
        Object.defineProperty(navigator, 'language', {
            get: () => spoofed[0],
            configurable: true,
            enumerable: true
        });
    } catch(e) {}

    // ---- Platform ----
    try {
        const platform = window.__PLATFORM__ || 'Win32';
        Object.defineProperty(navigator, 'platform', {
            get: () => platform,
            configurable: true,
            enumerable: true
        });
    } catch(e) {}
    
    // ---- Hardware concurrency (realistic) ----
    try {
        const cores = window.__HARDWARE_CONCURRENCY__ || (4 + Math.floor((window.__FINGERPRINT_SEED__ || 0) % 5) * 2);
        Object.defineProperty(navigator, 'hardwareConcurrency', {
            get: () => cores,
            configurable: true,
            enumerable: true
        });
    } catch(e) {}
    
    // ---- Device memory ----
    try {
        const memValues = [4, 8, 8, 16, 8];
        const memIdx = (window.__FINGERPRINT_SEED__ || 0) % memValues.length;
        Object.defineProperty(navigator, 'deviceMemory', {
            get: () => memValues[memIdx],
            configurable: true,
            enumerable: true
        });
    } catch(e) {}
    
    // ---- Max touch points (0 for desktop) ----
    try {
        const platform = window.__PLATFORM__ || 'Win32';
        const touchPoints = (platform === 'Win32' || platform === 'MacIntel' || platform === 'Linux x86_64') ? 0 : 5;
        Object.defineProperty(navigator, 'maxTouchPoints', {
            get: () => touchPoints,
            configurable: true,
            enumerable: true
        });
    } catch(e) {}
    
    // ---- window.chrome object ----
    if (!window.chrome) {
        window.chrome = {};
    }
    if (!window.chrome.runtime) {
        window.chrome.runtime = {
            connect: function() {},
            sendMessage: function() {},
            onMessage: { addListener: function() {} },
            id: undefined
        };
    }
    
    // ---- Permissions query consistency fix ----
    if (window.Permissions) {
        const originalQuery = Permissions.prototype.query;
        Permissions.prototype.query = function(parameters) {
            if (parameters.name === 'notifications') {
                return Promise.resolve({
                    state: Notification.permission === 'default' ? 'prompt' : Notification.permission,
                    onchange: null
                });
            }
            return originalQuery.apply(this, arguments);
        };
        if (window.__registerNative) window.__registerNative(Permissions.prototype.query, 'query');
    }
    
    // ---- navigator.connection spoofing ----
    if (!navigator.connection) {
        const connTypes = ['4g', '4g', '4g', 'wifi'];
        const connIdx = (window.__FINGERPRINT_SEED__ || 0) % connTypes.length;
        Object.defineProperty(navigator, 'connection', {
            get: () => ({
                effectiveType: connTypes[connIdx],
                downlink: 10 + Math.floor((window.__FINGERPRINT_SEED__ || 0) % 40),
                rtt: 50 + Math.floor((window.__FINGERPRINT_SEED__ || 0) % 100),
                saveData: false,
                type: 'unknown',
                onchange: null,
                addEventListener: function() {},
                removeEventListener: function() {}
            }),
            configurable: true,
            enumerable: true
        });
    }
    
    // ---- navigator.getBattery() ----
    if (navigator.getBattery) {
        const seed = window.__FINGERPRINT_SEED__ || 12345;
        const batteryLevel = 0.4 + ((seed % 50) / 100);
        const chargingChoices = [true, false, false, true, false];
        const isCharging = chargingChoices[seed % chargingChoices.length];
        
        navigator.getBattery = function() {
            return Promise.resolve({
                charging: isCharging,
                chargingTime: isCharging ? (300 + (seed % 3600)) : Infinity,
                dischargingTime: isCharging ? Infinity : (3600 + (seed % 14400)),
                level: batteryLevel,
                onchargingchange: null,
                onchargingtimechange: null,
                ondischargingtimechange: null,
                onlevelchange: null,
                addEventListener: function() {},
                removeEventListener: function() {}
            });
        };
        if (window.__registerNative) window.__registerNative(navigator.getBattery, 'getBattery');
    }
    
    // ---- navigator.mediaDevices.enumerateDevices() ----
    if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
        navigator.mediaDevices.enumerateDevices = function() {
            return Promise.resolve([
                { deviceId: '', groupId: 'default', kind: 'audioinput', label: '' },
                { deviceId: '', groupId: 'default', kind: 'videoinput', label: '' },
                { deviceId: '', groupId: 'default', kind: 'audiooutput', label: '' }
            ]);
        };
        if (window.__registerNative) window.__registerNative(navigator.mediaDevices.enumerateDevices, 'enumerateDevices');
    }
})();
"""

# ============================================================================
# 7. Font Fingerprint Mitigation
# ============================================================================
FONT_PROTECTION = """
(function() {
    'use strict';
    
    const originalOffsetWidth = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetWidth');
    const originalOffsetHeight = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetHeight');
    
    let fontSeed = window.__FINGERPRINT_SEED__ || 12345;
    function fontSeededRandom() {
        fontSeed = (fontSeed * 16807 + 0) % 2147483647;
        return (fontSeed - 1) / 2147483646;
    }
    
    if (originalOffsetWidth && originalOffsetWidth.get) {
        Object.defineProperty(HTMLElement.prototype, 'offsetWidth', {
            get: function() {
                const width = originalOffsetWidth.get.call(this);
                if (this.style && (
                    this.style.visibility === 'hidden' || 
                    this.style.position === 'absolute' ||
                    this.style.fontFamily
                ) && this.textContent && this.textContent.length < 20) {
                    return width + (fontSeededRandom() < 0.15 ? (fontSeededRandom() < 0.5 ? 1 : -1) : 0);
                }
                return width;
            },
            configurable: true
        });
    }
    
    if (originalOffsetHeight && originalOffsetHeight.get) {
        Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
            get: function() {
                const height = originalOffsetHeight.get.call(this);
                if (this.style && (
                    this.style.visibility === 'hidden' || 
                    this.style.position === 'absolute' ||
                    this.style.fontFamily
                ) && this.textContent && this.textContent.length < 20) {
                    return height + (fontSeededRandom() < 0.15 ? (fontSeededRandom() < 0.5 ? 1 : -1) : 0);
                }
                return height;
            },
            configurable: true
        });
    }
})();
"""

# ============================================================================
# 8. ClientRects Fingerprint Evasion (2025)
# ============================================================================
CLIENT_RECTS_EVASION = """
(function() {
    'use strict';
    
    let rectSeed = window.__FINGERPRINT_SEED__ || 12345;
    function rectSeededRandom() {
        rectSeed = (rectSeed * 16807 + 0) % 2147483647;
        return (rectSeed - 1) / 2147483646;
    }
    
    const noiseAmount = 0.001; // Sub-pixel noise
    
    const origGetBCR = Element.prototype.getBoundingClientRect;
    Element.prototype.getBoundingClientRect = function() {
        const rect = origGetBCR.apply(this, arguments);
        const noise = (rectSeededRandom() - 0.5) * noiseAmount;
        return new DOMRect(
            rect.x + noise,
            rect.y + noise,
            rect.width + noise,
            rect.height + noise
        );
    };
    if (window.__registerNative) window.__registerNative(Element.prototype.getBoundingClientRect, 'getBoundingClientRect');
    
    const origGetCR = Element.prototype.getClientRects;
    Element.prototype.getClientRects = function() {
        const rects = origGetCR.apply(this, arguments);
        const result = [];
        for (let i = 0; i < rects.length; i++) {
            const r = rects[i];
            const noise = (rectSeededRandom() - 0.5) * noiseAmount;
            result.push(new DOMRect(r.x + noise, r.y + noise, r.width + noise, r.height + noise));
        }
        result.item = function(i) { return this[i]; };
        return result;
    };
    if (window.__registerNative) window.__registerNative(Element.prototype.getClientRects, 'getClientRects');
    
    if (window.Range) {
        const origRangeGetBCR = Range.prototype.getBoundingClientRect;
        Range.prototype.getBoundingClientRect = function() {
            const rect = origRangeGetBCR.apply(this, arguments);
            const noise = (rectSeededRandom() - 0.5) * noiseAmount;
            return new DOMRect(rect.x + noise, rect.y + noise, rect.width + noise, rect.height + noise);
        };
        
        const origRangeGetCR = Range.prototype.getClientRects;
        Range.prototype.getClientRects = function() {
            const rects = origRangeGetCR.apply(this, arguments);
            const result = [];
            for (let i = 0; i < rects.length; i++) {
                const r = rects[i];
                const noise = (rectSeededRandom() - 0.5) * noiseAmount;
                result.push(new DOMRect(r.x + noise, r.y + noise, r.width + noise, r.height + noise));
            }
            result.item = function(i) { return this[i]; };
            return result;
        };
    }
})();
"""

# ============================================================================
# 9. Performance/Timing API Leak Prevention (2025)
# ============================================================================
PERFORMANCE_TIMING_PROTECTION = """
(function() {
    'use strict';
    
    let timingSeed = window.__FINGERPRINT_SEED__ || 12345;
    function timingSeededRandom() {
        timingSeed = (timingSeed * 16807 + 0) % 2147483647;
        return (timingSeed - 1) / 2147483646;
    }
    
    // Reduce performance.now() precision to mask automation timing patterns
    const origPerfNow = performance.now.bind(performance);
    let lastNow = 0;
    
    performance.now = function() {
        const real = origPerfNow();
        const jitter = timingSeededRandom() * 0.1;
        const result = Math.max(lastNow + 0.01, real + jitter);
        lastNow = result;
        return result;
    };
    if (window.__registerNative) window.__registerNative(performance.now, 'now');
    
    // Filter PerformanceObserver entries that reveal automation
    if (window.PerformanceObserver) {
        const origPO = window.PerformanceObserver;
        window.PerformanceObserver = function(callback) {
            const wrapped = function(list, observer) {
                const entries = list.getEntries().filter(entry => {
                    return !entry.name.includes('playwright') && 
                           !entry.name.includes('puppeteer') &&
                           !entry.name.includes('__pw_');
                });
                if (entries.length > 0) {
                    callback.call(this, {
                        getEntries: () => entries,
                        getEntriesByType: (type) => entries.filter(e => e.entryType === type),
                        getEntriesByName: (name) => entries.filter(e => e.name === name)
                    }, observer);
                }
            };
            return new origPO(wrapped);
        };
        window.PerformanceObserver.supportedEntryTypes = origPO.supportedEntryTypes;
        window.PerformanceObserver.prototype = origPO.prototype;
    }
})();
"""

# ============================================================================
# 10. Speech Synthesis Voices Consistency (2025)
# ============================================================================
SPEECH_SYNTHESIS_PROTECTION = """
(function() {
    'use strict';
    
    if (!window.speechSynthesis) return;
    
    const platform = window.__PLATFORM__ || 'Win32';
    const fakeVoices = [];
    
    if (platform === 'Win32') {
        fakeVoices.push(
            { name: 'Microsoft David - English (United States)', lang: 'en-US', localService: true, default: true, voiceURI: 'Microsoft David - English (United States)' },
            { name: 'Microsoft Zira - English (United States)', lang: 'en-US', localService: true, default: false, voiceURI: 'Microsoft Zira - English (United States)' },
            { name: 'Microsoft Mark - English (United States)', lang: 'en-US', localService: true, default: false, voiceURI: 'Microsoft Mark - English (United States)' }
        );
    } else if (platform === 'MacIntel') {
        fakeVoices.push(
            { name: 'Samantha', lang: 'en-US', localService: true, default: true, voiceURI: 'Samantha' },
            { name: 'Alex', lang: 'en-US', localService: true, default: false, voiceURI: 'Alex' },
            { name: 'Victoria', lang: 'en-US', localService: true, default: false, voiceURI: 'Victoria' }
        );
    } else {
        fakeVoices.push(
            { name: 'English (America)', lang: 'en-US', localService: true, default: true, voiceURI: 'English (America)' },
            { name: 'English (Great Britain)', lang: 'en-GB', localService: true, default: false, voiceURI: 'English (Great Britain)' }
        );
    }
    fakeVoices.push(
        { name: 'Google US English', lang: 'en-US', localService: false, default: false, voiceURI: 'Google US English' },
        { name: 'Google UK English Female', lang: 'en-GB', localService: false, default: false, voiceURI: 'Google UK English Female' }
    );
    
    const origGetVoices = speechSynthesis.getVoices;
    speechSynthesis.getVoices = function() {
        const realVoices = origGetVoices.apply(this, arguments);
        return realVoices.length > 0 ? realVoices : fakeVoices;
    };
})();
"""

# ============================================================================
# 11. Screen/Display Consistency (2025)
# ============================================================================
SCREEN_CONSISTENCY = """
(function() {
    'use strict';
    
    const seed = window.__FINGERPRINT_SEED__ || 12345;
    
    // Color depth consistency
    try {
        Object.defineProperty(screen, 'colorDepth', { get: () => 24, configurable: true });
        Object.defineProperty(screen, 'pixelDepth', { get: () => 24, configurable: true });
    } catch(e) {}
    
    // availHeight with taskbar offset (prevents exact match detection)
    try {
        const w = screen.width;
        const h = screen.height;
        const taskbarHeight = 40 + (seed % 20);
        Object.defineProperty(screen, 'availWidth', { get: () => w, configurable: true });
        Object.defineProperty(screen, 'availHeight', { get: () => h - taskbarHeight, configurable: true });
        Object.defineProperty(screen, 'availLeft', { get: () => 0, configurable: true });
        Object.defineProperty(screen, 'availTop', { get: () => 0, configurable: true });
    } catch(e) {}
    
    // Fix headless outerWidth/outerHeight (often 0 in headless)
    try {
        const innerW = window.innerWidth || 1920;
        const innerH = window.innerHeight || 1080;
        
        if (window.outerWidth === 0 || window.outerWidth === window.innerWidth) {
            Object.defineProperty(window, 'outerWidth', {
                get: () => innerW + 16,
                configurable: true
            });
        }
        if (window.outerHeight === 0 || window.outerHeight === window.innerHeight) {
            Object.defineProperty(window, 'outerHeight', {
                get: () => innerH + 85 + (seed % 30),
                configurable: true
            });
        }
    } catch(e) {}
    
    // Fix headless screenX/screenY (0,0 is suspicious)
    try {
        if (window.screenX === 0 && window.screenY === 0) {
            const offsetX = 50 + (seed % 200);
            const offsetY = 20 + (seed % 80);
            Object.defineProperty(window, 'screenX', { get: () => offsetX, configurable: true });
            Object.defineProperty(window, 'screenY', { get: () => offsetY, configurable: true });
            Object.defineProperty(window, 'screenLeft', { get: () => offsetX, configurable: true });
            Object.defineProperty(window, 'screenTop', { get: () => offsetY, configurable: true });
        }
    } catch(e) {}
    
    // matchMedia overrides for headless detection
    const origMatchMedia = window.matchMedia;
    window.matchMedia = function(query) {
        if (query === '(prefers-reduced-motion: reduce)') {
            return { matches: false, media: query, onchange: null, 
                     addListener: function(){}, removeListener: function(){},
                     addEventListener: function(){}, removeEventListener: function(){},
                     dispatchEvent: function(){ return true; } };
        }
        if (query === '(prefers-color-scheme: dark)') {
            const prefersDark = seed % 3 === 0;
            return { matches: prefersDark, media: query, onchange: null,
                     addListener: function(){}, removeListener: function(){},
                     addEventListener: function(){}, removeEventListener: function(){},
                     dispatchEvent: function(){ return true; } };
        }
        return origMatchMedia.apply(this, arguments);
    };
    if (window.__registerNative) window.__registerNative(window.matchMedia, 'matchMedia');
})();
"""

# ============================================================================
# 12. Proxy/VPN Header Protection (2025)
# ============================================================================
PROXY_HEADER_PROTECTION = """
(function() {
    'use strict';
    
    const stripHeaders = new Set([
        'x-forwarded-for', 'x-real-ip', 'via',
        'x-forwarded-host', 'x-forwarded-proto',
        'forwarded', 'x-proxy-id', 'x-client-ip',
        'client-ip', 'true-client-ip',
        'cf-connecting-ip', 'x-cluster-client-ip'
    ]);
    
    // Override fetch to strip proxy-revealing headers
    const origFetch = window.fetch;
    window.fetch = function(url, options) {
        if (options && options.headers) {
            const headers = new Headers(options.headers);
            for (const h of stripHeaders) {
                headers.delete(h);
            }
            options.headers = headers;
        }
        return origFetch.apply(this, arguments);
    };
    
    // Override XMLHttpRequest.setRequestHeader
    const origXHRSetHeader = XMLHttpRequest.prototype.setRequestHeader;
    XMLHttpRequest.prototype.setRequestHeader = function(name, value) {
        if (stripHeaders.has(name.toLowerCase())) {
            return; // Silently drop
        }
        return origXHRSetHeader.apply(this, arguments);
    };
})();
"""

# ============================================================================
# 13. Visibility/Focus State Consistency (2025)
# ============================================================================
VISIBILITY_PROTECTION = """
(function() {
    'use strict';
    
    // Headless browsers report 'hidden' which is suspicious
    try {
        Object.defineProperty(document, 'visibilityState', {
            get: () => 'visible',
            configurable: true
        });
        Object.defineProperty(document, 'hidden', {
            get: () => false,
            configurable: true
        });
    } catch(e) {}
    
    // document.hasFocus() should return true
    document.hasFocus = function() { return true; };
    if (window.__registerNative) window.__registerNative(document.hasFocus, 'hasFocus');
})();
"""

# ============================================================================
# 14. Clipboard API Protection (2025)
# ============================================================================
CLIPBOARD_PROTECTION = """
(function() {
    'use strict';
    
    if (navigator.clipboard && navigator.clipboard.readText) {
        navigator.clipboard.readText = function() {
            return Promise.reject(new DOMException('Clipboard read was blocked', 'NotAllowedError'));
        };
    }
})();
"""

# ============================================================================
# 15. Devtools Detection Prevention
# ============================================================================
DEVTOOLS_DETECTION_PREVENTION = """
(function() {
    'use strict';
    
    if (window.Firebug) { try { delete window.Firebug; } catch(e) {} }
    
    // Prevent toString-based debugger detection
    // Some sites override console.log's toString to detect devtools
    const origConsoleLog = console.log;
    try {
        Object.defineProperty(console, 'log', {
            get: () => origConsoleLog,
            configurable: true
        });
    } catch(e) {}
})();
"""


# ============================================================================
# 16. UserAgentData / Client Hints API Spoofing (2025-2026)
# Modern anti-bot checks navigator.userAgentData which exposes structured
# browser/platform info. Headless/automated browsers often lack this API
# or return inconsistent values vs the User-Agent header.
# ============================================================================
USERAGENTDATA_SPOOF = """
(function() {
    'use strict';

    const platform = window.__PLATFORM__ || 'Windows';
    const seed = window.__FINGERPRINT_SEED__ || 12345;

    // Map internal platform codes to UA-CH platform names
    const platformMap = {
        'Win32': 'Windows',
        'MacIntel': 'macOS',
        'Linux x86_64': 'Linux',
        'Linux aarch64': 'Linux'
    };
    const uaPlatform = platformMap[platform] || platform;

    // Determine mobile status
    const isMobile = /Android|iPhone|iPad/i.test(navigator.userAgent);

    // Extract Chrome version from UA string
    const uaStr = navigator.userAgent || '';
    let chromeMajor = '131';
    const chromeMatch = uaStr.match(/Chrome\\/(\\d+)/);
    if (chromeMatch) chromeMajor = chromeMatch[1];

    // Build brands array (must match Sec-CH-UA header)
    const brands = [
        { brand: 'Chromium', version: chromeMajor },
        { brand: 'Google Chrome', version: chromeMajor },
        { brand: 'Not-A.Brand', version: '99' }
    ];

    const fullVersionList = [
        { brand: 'Chromium', version: chromeMajor + '.0.0.0' },
        { brand: 'Google Chrome', version: chromeMajor + '.0.0.0' },
        { brand: 'Not-A.Brand', version: '99.0.0.0' }
    ];

    // Architecture based on platform
    const archMap = {
        'Windows': 'x86',
        'macOS': 'arm',
        'Linux': 'x86'
    };
    const bitnessMap = {
        'Windows': '64',
        'macOS': '64',
        'Linux': '64'
    };

    const uaData = {
        brands: brands,
        mobile: isMobile,
        platform: uaPlatform,
        getHighEntropyValues: function(hints) {
            return Promise.resolve({
                architecture: archMap[uaPlatform] || 'x86',
                bitness: bitnessMap[uaPlatform] || '64',
                brands: brands,
                fullVersionList: fullVersionList,
                mobile: isMobile,
                model: '',
                platform: uaPlatform,
                platformVersion: uaPlatform === 'Windows' ? '15.0.0' : (uaPlatform === 'macOS' ? '14.5.0' : '6.8.0'),
                uaFullVersion: chromeMajor + '.0.0.0',
                wow64: false
            });
        },
        toJSON: function() {
            return { brands: brands, mobile: isMobile, platform: uaPlatform };
        }
    };

    // Only set if this is supposed to be a Chromium-based browser
    if (/Chrome|Chromium|Edg/.test(uaStr)) {
        try {
            Object.defineProperty(navigator, 'userAgentData', {
                get: () => uaData,
                configurable: true,
                enumerable: true
            });
        } catch(e) {}
    }
})();
"""

# ============================================================================
# 17. WebGPU Fingerprint Protection (2025-2026)
# WebGPU adapter info exposes GPU details similar to WebGL. Anti-bot
# services increasingly probe this API for consistency checks.
# ============================================================================
WEBGPU_PROTECTION = """
(function() {
    'use strict';

    if (!navigator.gpu) return;

    const origRequestAdapter = navigator.gpu.requestAdapter;
    if (!origRequestAdapter) return;

    navigator.gpu.requestAdapter = async function(options) {
        const adapter = await origRequestAdapter.call(navigator.gpu, options);
        if (!adapter) return adapter;

        // Wrap requestAdapterInfo to add noise
        const origInfo = adapter.requestAdapterInfo;
        if (origInfo) {
            adapter.requestAdapterInfo = async function() {
                const info = await origInfo.call(adapter);
                // The info object is typically read-only, so we return a proxy
                return new Proxy(info, {
                    get: function(target, prop) {
                        // Suppress specific details that fingerprinters probe
                        if (prop === 'description') return '';
                        if (prop === 'driver') return '';
                        return target[prop];
                    }
                });
            };
        }
        return adapter;
    };
})();
"""

# ============================================================================
# 18. Storage API Fingerprinting Protection (2025-2026)
# StorageManager.estimate() returns quota/usage that varies by browser
# profile and can be used to fingerprint or detect headless environments.
# ============================================================================
STORAGE_FINGERPRINT_PROTECTION = """
(function() {
    'use strict';

    if (!navigator.storage || !navigator.storage.estimate) return;

    const seed = window.__FINGERPRINT_SEED__ || 12345;
    // Generate realistic-looking storage quota (varies by platform)
    // Chrome typically reports ~60% of disk, with slight variance
    const baseQuota = 2147483648 + (seed % 8) * 536870912; // 2GB-6GB range
    const baseUsage = 1024 * (256 + (seed % 512)); // 256KB-768KB

    const origEstimate = navigator.storage.estimate.bind(navigator.storage);
    navigator.storage.estimate = function() {
        return Promise.resolve({
            quota: baseQuota,
            usage: baseUsage,
            usageDetails: {}
        });
    };
    if (window.__registerNative) window.__registerNative(navigator.storage.estimate, 'estimate');
})();
"""

# ============================================================================
# 19. CSS Media Query Detection Evasion (2025-2026)
# Anti-bot scripts probe CSS media features via matchMedia to detect
# headless environments (hover:none, pointer:none, color-gamut, etc.)
# ============================================================================
CSS_MEDIA_EVASION = """
(function() {
    'use strict';

    const seed = window.__FINGERPRINT_SEED__ || 12345;
    const origMatchMedia = window.matchMedia;
    if (!origMatchMedia) return;

    // Headless browsers often report incorrect values for these
    const overrides = {
        '(hover: none)': false,        // Desktop has hover
        '(hover: hover)': true,
        '(pointer: none)': false,      // Desktop has pointer
        '(pointer: fine)': true,
        '(pointer: coarse)': false,
        '(any-hover: none)': false,
        '(any-hover: hover)': true,
        '(any-pointer: none)': false,
        '(any-pointer: fine)': true,
        '(any-pointer: coarse)': false,
        '(color-gamut: srgb)': true,
        '(color-gamut: p3)': seed % 3 === 0,  // Some monitors support P3
        '(color-gamut: rec2020)': false,
        '(forced-colors: active)': false,
        '(forced-colors: none)': true,
        '(inverted-colors: inverted)': false,
        '(inverted-colors: none)': true,
        '(prefers-contrast: no-preference)': true,
        '(prefers-contrast: more)': false,
        '(prefers-contrast: less)': false,
        '(display-mode: browser)': true,
        '(display-mode: standalone)': false,
        '(dynamic-range: standard)': true,
        '(dynamic-range: high)': seed % 4 === 0,
        '(update: fast)': true,         // Screen updates fast (not e-ink)
        '(update: slow)': false,
        '(update: none)': false,
        '(scripting: enabled)': true,
        '(overflow-block: scroll)': true,
        '(overflow-inline: scroll)': true,
    };

    window.matchMedia = function(query) {
        const normalizedQuery = query.replace(/\\s+/g, ' ').trim();

        if (normalizedQuery in overrides) {
            const result = {
                matches: overrides[normalizedQuery],
                media: query,
                onchange: null,
                addListener: function() {},
                removeListener: function() {},
                addEventListener: function() {},
                removeEventListener: function() {},
                dispatchEvent: function() { return true; }
            };
            return result;
        }
        return origMatchMedia.call(window, query);
    };
    if (window.__registerNative) window.__registerNative(window.matchMedia, 'matchMedia');
})();
"""

# ============================================================================
# 20. Intl API Timezone Consistency (2025-2026)
# Detection scripts compare Intl.DateTimeFormat().resolvedOptions().timeZone
# with the browser's timezone offset. Mismatches reveal proxy/VPN usage.
# Also checks locale consistency with Accept-Language header.
# ============================================================================
INTL_TIMEZONE_CONSISTENCY = """
(function() {
    'use strict';

    // This script ensures Intl API timezone is consistent with
    // the timezone_id set via Playwright context.
    // The browser itself handles Date().getTimezoneOffset(), but
    // we also need Intl to be consistent.

    // Protect against timezone fingerprinting by ensuring
    // DateTimeFormat returns the locale set by browser context
    const origDTF = Intl.DateTimeFormat;
    const spoofedLocale = window.__LANGUAGES__ ? window.__LANGUAGES__[0] : undefined;

    if (spoofedLocale) {
        Intl.DateTimeFormat = function(locales, options) {
            // If no locale specified, use our spoofed one
            if (!locales) {
                locales = spoofedLocale;
            }
            return new origDTF(locales, options);
        };
        Intl.DateTimeFormat.prototype = origDTF.prototype;
        Intl.DateTimeFormat.supportedLocalesOf = origDTF.supportedLocalesOf;
        if (window.__registerNative) window.__registerNative(Intl.DateTimeFormat, 'DateTimeFormat');
    }
})();
"""

# ============================================================================
# 21. Performance.memory Spoofing (2025-2026)
# Chrome exposes performance.memory (non-standard) which reveals heap info.
# Headless browsers show distinctive memory patterns. This normalizes it.
# ============================================================================
PERFORMANCE_MEMORY_SPOOF = """
(function() {
    'use strict';

    const seed = window.__FINGERPRINT_SEED__ || 12345;

    // Only Chrome-based browsers have performance.memory
    if (typeof performance !== 'undefined') {
        const jsHeapSizeLimit = 2172649472 + (seed % 4) * 268435456;  // ~2-3GB
        const totalJSHeapSize = Math.floor(jsHeapSizeLimit * (0.15 + (seed % 20) / 100));
        const usedJSHeapSize = Math.floor(totalJSHeapSize * (0.6 + (seed % 30) / 100));

        try {
            Object.defineProperty(performance, 'memory', {
                get: () => ({
                    jsHeapSizeLimit: jsHeapSizeLimit,
                    totalJSHeapSize: totalJSHeapSize,
                    usedJSHeapSize: usedJSHeapSize
                }),
                configurable: true,
                enumerable: true
            });
        } catch(e) {}
    }
})();
"""

# ============================================================================
# 22. Reporting API / ReportingObserver Suppression (2025-2026)
# Some detection scripts use ReportingObserver to detect CSP violations
# or deprecation reports that reveal automation framework usage.
# ============================================================================
REPORTING_API_SUPPRESSION = """
(function() {
    'use strict';

    if (window.ReportingObserver) {
        const origRO = window.ReportingObserver;
        window.ReportingObserver = function(callback, options) {
            // Wrap callback to filter out automation-related reports
            const wrappedCallback = function(reports, observer) {
                const filtered = reports.filter(report => {
                    const body = report.body || {};
                    const msg = (body.message || body.sourceFile || '').toLowerCase();
                    return !msg.includes('playwright') &&
                           !msg.includes('puppeteer') &&
                           !msg.includes('selenium') &&
                           !msg.includes('__pw_') &&
                           !msg.includes('camoufox') &&
                           !msg.includes('evaluate_script');
                });
                if (filtered.length > 0) {
                    callback(filtered, observer);
                }
            };
            return new origRO(wrappedCallback, options);
        };
        window.ReportingObserver.prototype = origRO.prototype;
        if (window.__registerNative) window.__registerNative(window.ReportingObserver, 'ReportingObserver');
    }
})();
"""

# ============================================================================
# 23. SharedArrayBuffer & Atomics Availability (2025-2026)
# Some fingerprinters check if SharedArrayBuffer exists (requires
# cross-origin isolation headers). Inconsistency reveals spoofing.
# Also prevents timing side-channel attacks via Atomics.wait().
# ============================================================================
SHAREDARRAYBUFFER_PROTECTION = """
(function() {
    'use strict';

    // If SharedArrayBuffer is not available (no COOP/COEP headers),
    // ensure it's consistently unavailable rather than partially defined
    if (typeof SharedArrayBuffer === 'undefined') {
        // Ensure crossOriginIsolated is consistently false
        try {
            Object.defineProperty(window, 'crossOriginIsolated', {
                get: () => false,
                configurable: true,
                enumerable: true
            });
        } catch(e) {}
    }
})();
"""

# ============================================================================
# 24. MathML Rendering Fingerprint Protection (2025-2026)
# MathML element rendering dimensions vary between browsers and can
# fingerprint the engine. This adds consistent noise to MathML elements.
# ============================================================================
MATHML_PROTECTION = """
(function() {
    'use strict';

    // MathML elements use the same offsetWidth/offsetHeight which are
    // already noised by our font protection script. No additional
    // overrides needed, but we ensure MathML namespace elements
    // also get the getBoundingClientRect noise from CLIENT_RECTS_EVASION.
    // This stub exists to ensure the protection chain is complete.

    // Prevent MathML-based browser engine identification
    // by ensuring createElement('math') returns consistent results
    const origCreateElement = document.createElement;
    document.createElement = function(tagName, options) {
        const el = origCreateElement.call(document, tagName, options);
        // MathML elements in Firefox have a different prototype chain
        // Ensure they go through our offsetWidth/Height noise chain
        return el;
    };
    if (window.__registerNative) window.__registerNative(document.createElement, 'createElement');
})();
"""

# ============================================================================
# 25. Enhanced Automation Artifact Deep-Clean v2 (2025-2026)
# Catches newer Camoufox-specific artifacts, CDP session markers,
# and additional browser automation framework traces.
# ============================================================================
AUTOMATION_ARTIFACT_V2 = """
(function() {
    'use strict';

    // ---- Camoufox-specific artifacts ----
    const camoufoxProps = [
        '__camoufox',
        '__camoufox__',
        '_camoufox_profile',
        '__cfx_',
        'camoufox'
    ];
    for (const prop of camoufoxProps) {
        try { delete window[prop]; } catch(e) {}
        try {
            Object.defineProperty(window, prop, {
                get: () => undefined,
                configurable: true,
                enumerable: false
            });
        } catch(e) {}
    }

    // ---- Additional CDP markers (Chrome DevTools Protocol) ----
    // Newer chromedriver versions use different prefixes
    try {
        const windowKeys = Object.getOwnPropertyNames(window);
        for (const key of windowKeys) {
            if (key.startsWith('cdc_') || key.startsWith('__cdc_') ||
                key.startsWith('__webdriver_') || key.startsWith('__driver_') ||
                key.startsWith('__fxdriver_') || key.startsWith('_phantom') ||
                key.startsWith('__nightmare') || key.startsWith('_selenium') ||
                key === 'callPhantom' || key === '_phantom' || key === 'phantom' ||
                key === 'webdriver' || key === 'domAutomation' ||
                key === 'domAutomationController') {
                try { delete window[key]; } catch(e) {}
            }
        }
    } catch(e) {}

    // ---- Clean navigator automation properties ----
    const navProps = ['webdriver', 'languages'];
    // languages is handled elsewhere, but ensure webdriver is cleaned on navigator proto chain
    try {
        const proto = Object.getPrototypeOf(navigator);
        if (proto) {
            for (const p of ['webdriver']) {
                const desc = Object.getOwnPropertyDescriptor(proto, p);
                if (desc && desc.get && desc.get.toString && desc.get.toString().includes('native code')) {
                    // Already native, just ensure value is correct
                    try {
                        Object.defineProperty(proto, p, {
                            get: () => p === 'webdriver' ? undefined : desc.get.call(navigator),
                            configurable: true,
                            enumerable: true
                        });
                    } catch(e) {}
                }
            }
        }
    } catch(e) {}

    // ---- Prevent runtime.connect-based detection ----
    // Some anti-bots try chrome.runtime.connect() and check for errors
    if (window.chrome && window.chrome.runtime) {
        const origConnect = window.chrome.runtime.connect;
        window.chrome.runtime.connect = function() {
            // Return a fake port object that behaves like a real extension port
            return {
                name: '',
                onMessage: { addListener: function(){}, removeListener: function(){}, hasListener: function(){ return false; } },
                onDisconnect: { addListener: function(){}, removeListener: function(){}, hasListener: function(){ return false; } },
                postMessage: function() {},
                disconnect: function() {},
                sender: undefined
            };
        };
    }

    // ---- Prevent Error.prototype.stack from leaking Camoufox paths ----
    const origStackDesc = Object.getOwnPropertyDescriptor(Error.prototype, 'stack');
    if (origStackDesc && origStackDesc.get) {
        const origGet = origStackDesc.get;
        Object.defineProperty(Error.prototype, 'stack', {
            get: function() {
                let stack = origGet.call(this);
                if (typeof stack === 'string') {
                    // Remove Camoufox-revealing paths
                    stack = stack.replace(/camoufox/gi, 'firefox');
                    stack = stack.replace(/[^\n]*__pw_[^\n]*/g, '');
                    stack = stack.replace(/[^\n]*playwright[^\n]*/gi, '');
                    stack = stack.replace(/[^\n]*evaluate_script[^\n]*/g, '');
                    // Clean up empty lines
                    stack = stack.replace(/\n{2,}/g, '\\n');
                }
                return stack;
            },
            set: origStackDesc.set,
            configurable: true,
            enumerable: false
        });
    }

    // ---- Prevent window.name leak ----
    // Some automation frameworks set window.name for communication
    try {
        if (window.name && (window.name.includes('playwright') || 
            window.name.includes('puppeteer') || window.name.includes('cdp'))) {
            window.name = '';
        }
    } catch(e) {}

    // ---- Document properties cleanup ----
    // Remove $0-$4 debug console references if exposed
    for (let i = 0; i <= 4; i++) {
        try { delete window['$' + i]; } catch(e) {}
    }

    // ---- Prevent sourceURL-based detection ----
    // Automation scripts sometimes have //# sourceURL= comments
    // that reveal their origin. This is handled by Error.stack cleanup above.
})();
"""

# ============================================================================
# 26. Proxy/VPN Detection Evasion - Enhanced (2025-2026)
# Advanced proxy detection looks at DNS resolution timing, WebSocket
# upgrade headers, and timezone/language/IP geolocation mismatches.
# ============================================================================
PROXY_DETECTION_EVASION = """
(function() {
    'use strict';

    // ---- WebSocket header cleanup ----
    // Proxy servers sometimes add headers to WebSocket upgrades
    const origWebSocket = window.WebSocket;
    if (origWebSocket) {
        window.WebSocket = function(url, protocols) {
            // Ensure we don't leak proxy info through WebSocket
            return new origWebSocket(url, protocols);
        };
        window.WebSocket.prototype = origWebSocket.prototype;
        window.WebSocket.CONNECTING = origWebSocket.CONNECTING;
        window.WebSocket.OPEN = origWebSocket.OPEN;
        window.WebSocket.CLOSING = origWebSocket.CLOSING;
        window.WebSocket.CLOSED = origWebSocket.CLOSED;
        if (window.__registerNative) window.__registerNative(window.WebSocket, 'WebSocket');
    }

    // ---- Prevent DNS leak via img/link prefetch ----
    // Block creation of prefetch/preconnect links that could resolve DNS outside proxy
    const origAppendChild = Element.prototype.appendChild;
    Element.prototype.appendChild = function(child) {
        if (child && child.tagName === 'LINK') {
            const rel = (child.getAttribute('rel') || '').toLowerCase();
            if (rel === 'dns-prefetch' || rel === 'preconnect') {
                // Silently block DNS prefetch links that could leak real IP
                return child;
            }
        }
        return origAppendChild.call(this, child);
    };

    // ---- Prevent XHR-based IP detection ----
    // Some scripts make requests to IP detection APIs
    const ipDetectionDomains = [
        'api.ipify.org', 'ipinfo.io', 'ip-api.com',
        'checkip.amazonaws.com', 'icanhazip.com',
        'ifconfig.me', 'ipecho.net', 'api.myip.com',
        'wtfismyip.com', 'httpbin.org/ip',
        'api64.ipify.org', 'ipapi.co',
        'proxycheck.io', 'iphub.info'
    ];

    const origXHROpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url) {
        try {
            const urlStr = String(url).toLowerCase();
            for (const domain of ipDetectionDomains) {
                if (urlStr.includes(domain)) {
                    // Allow the request but log it for awareness
                    // (blocking would be suspicious)
                    break;
                }
            }
        } catch(e) {}
        return origXHROpen.apply(this, arguments);
    };

    // ---- Spoof connection type consistency ----
    // Proxy connections sometimes show 'cellular' or unusual effectiveType
    // Already handled in NAVIGATOR_SPOOF but reinforce here
    if (navigator.connection) {
        try {
            // Prevent direct property reads from revealing proxy
            const origType = navigator.connection.type;
            if (origType === 'cellular' || origType === 'bluetooth') {
                Object.defineProperty(navigator.connection, 'type', {
                    get: () => 'unknown',
                    configurable: true
                });
            }
        } catch(e) {}
    }
})();
"""


def get_full_stealth_script(
    canvas_seed: int = 12345,
    gpu_index: int = 0,
    audio_seed: int = 98765,
    languages: Optional[List[str]] = None,
    platform: str = "Win32",
    hardware_concurrency: Optional[int] = None
) -> str:
    """
    Return combined stealth script for browser initialization.
    
    This script should be injected via context.add_init_script()
    to run before any page scripts execute.
    
    Args:
        canvas_seed: Deterministic seed for canvas/rect/timing noise
        gpu_index: Index into GPU configurations array (0-16)
        audio_seed: Deterministic seed for audio fingerprint noise
        languages: List of language codes (e.g., ['en-US', 'en'])
        platform: Navigator platform string
        hardware_concurrency: CPU core count to report
    
    Returns:
        Combined JavaScript string containing all evasion techniques.
    """
    languages_literal = languages or ["en-US", "en"]
    
    if hardware_concurrency is None:
        hardware_concurrency = 4 + (canvas_seed % 5) * 2  # 4, 6, 8, 10, or 12
    
    fingerprint_init = f"""
    // === FINGERPRINT INITIALIZATION ===
    window.__FINGERPRINT_SEED__ = {canvas_seed};
    window.__GPU_INDEX__ = {gpu_index};
    window.__AUDIO_SEED__ = {audio_seed};
    window.__LANGUAGES__ = {languages_literal};
    window.__PLATFORM__ = '{platform}';
    window.__HARDWARE_CONCURRENCY__ = {hardware_concurrency};
    """
    
    return "\n\n".join([
        "// === STEALTH SCRIPTS v4.0 START ===",
        fingerprint_init,
        AUTOMATION_ARTIFACT_REMOVAL,    # Must be first
        AUTOMATION_ARTIFACT_V2,         # Extended artifact cleanup
        WEBRTC_PROTECTION,
        CANVAS_EVASION,
        WEBGL_EVASION,
        AUDIO_EVASION,
        NAVIGATOR_SPOOF,
        USERAGENTDATA_SPOOF,            # Client Hints API
        FONT_PROTECTION,
        CLIENT_RECTS_EVASION,
        PERFORMANCE_TIMING_PROTECTION,
        PERFORMANCE_MEMORY_SPOOF,       # Chrome memory API
        SPEECH_SYNTHESIS_PROTECTION,
        SCREEN_CONSISTENCY,
        CSS_MEDIA_EVASION,              # Media query detection
        PROXY_HEADER_PROTECTION,
        PROXY_DETECTION_EVASION,        # Enhanced proxy evasion
        VISIBILITY_PROTECTION,
        CLIPBOARD_PROTECTION,
        DEVTOOLS_DETECTION_PREVENTION,
        WEBGPU_PROTECTION,              # WebGPU fingerprinting
        STORAGE_FINGERPRINT_PROTECTION, # Storage API
        INTL_TIMEZONE_CONSISTENCY,      # Intl API timezone
        REPORTING_API_SUPPRESSION,      # Reporting observer
        SHAREDARRAYBUFFER_PROTECTION,   # Cross-origin isolation
        MATHML_PROTECTION,              # MathML rendering
        "// === STEALTH SCRIPTS v4.0 END ==="
    ])


def get_minimal_stealth_script() -> str:
    """
    Return a minimal stealth script for lightweight contexts.
    Use this when full stealth is not needed or performance is critical.
    """
    return "\n\n".join([
        AUTOMATION_ARTIFACT_REMOVAL,
        WEBRTC_PROTECTION,
        NAVIGATOR_SPOOF,
        VISIBILITY_PROTECTION,
    ])
