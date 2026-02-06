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
        "// === STEALTH SCRIPTS v3.0 START ===",
        fingerprint_init,
        AUTOMATION_ARTIFACT_REMOVAL,    # Must be first
        WEBRTC_PROTECTION,
        CANVAS_EVASION,
        WEBGL_EVASION,
        AUDIO_EVASION,
        NAVIGATOR_SPOOF,
        FONT_PROTECTION,
        CLIENT_RECTS_EVASION,           # NEW
        PERFORMANCE_TIMING_PROTECTION,  # NEW
        SPEECH_SYNTHESIS_PROTECTION,    # NEW
        SCREEN_CONSISTENCY,             # NEW
        PROXY_HEADER_PROTECTION,        # NEW
        VISIBILITY_PROTECTION,          # NEW
        CLIPBOARD_PROTECTION,           # NEW
        DEVTOOLS_DETECTION_PREVENTION,  # NEW
        "// === STEALTH SCRIPTS v3.0 END ==="
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
