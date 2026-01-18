"""
Tests for browser stealth scripts module.
"""

import pytest
from browser.stealth_scripts import (
    get_full_stealth_script, 
    get_minimal_stealth_script,
    CANVAS_EVASION,
    WEBGL_EVASION,
    AUDIO_EVASION,
    NAVIGATOR_SPOOF,
    WEBRTC_PROTECTION,
    FONT_PROTECTION
)


class TestStealthScripts:
    """Tests for stealth script generation."""
    
    def test_full_stealth_script_not_empty(self):
        """Verify full stealth script is properly composed."""
        script = get_full_stealth_script()
        assert len(script) > 500, "Full stealth script should be substantial"
        assert "webdriver" in script.lower()
        assert "canvas" in script.lower() or "todataurl" in script.lower()
    
    def test_minimal_stealth_script_not_empty(self):
        """Verify minimal script contains essentials."""
        script = get_minimal_stealth_script()
        assert len(script) > 100
        assert "webdriver" in script.lower()
    
    def test_webrtc_protection_contains_rtc(self):
        """Verify WebRTC protection script addresses peer connections."""
        assert "RTCPeerConnection" in WEBRTC_PROTECTION
        assert "iceServers" in WEBRTC_PROTECTION
    
    def test_canvas_evasion_modifies_todataurl(self):
        """Verify Canvas evasion overrides toDataURL."""
        assert "toDataURL" in CANVAS_EVASION
        assert "getImageData" in CANVAS_EVASION
    
    def test_webgl_evasion_spoofs_vendor(self):
        """Verify WebGL evasion spoofs vendor info."""
        assert "UNMASKED_VENDOR_WEBGL" in CANVAS_EVASION or "37445" in WEBGL_EVASION
        assert "getParameter" in WEBGL_EVASION
    
    def test_audio_evasion_modifies_channel_data(self):
        """Verify Audio evasion adds noise to audio data."""
        assert "getChannelData" in AUDIO_EVASION
        # Should add random noise
        assert "random" in AUDIO_EVASION.lower()
    
    def test_navigator_spoof_hides_webdriver(self):
        """Verify Navigator spoofing hides automation flags."""
        assert "webdriver" in NAVIGATOR_SPOOF
        assert "plugins" in NAVIGATOR_SPOOF
    
    def test_font_protection_exists(self):
        """Verify Font protection script is defined."""
        assert len(FONT_PROTECTION) > 0
        assert "offsetWidth" in FONT_PROTECTION or "font" in FONT_PROTECTION.lower()
    
    def test_scripts_are_valid_js_syntax(self):
        """Basic check that scripts don't have obvious syntax errors."""
        scripts = [
            WEBRTC_PROTECTION,
            CANVAS_EVASION,
            WEBGL_EVASION,
            AUDIO_EVASION,
            NAVIGATOR_SPOOF,
            FONT_PROTECTION
        ]
        for script in scripts:
            # Check balanced parentheses
            assert script.count('(') == script.count(')'), "Unbalanced parentheses"
            assert script.count('{') == script.count('}'), "Unbalanced braces"
