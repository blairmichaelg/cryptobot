"""
Browser module for Cryptobot Gen 3.0.

Provides anti-detection browser automation built on top of Camoufox (a hardened
Firefox fork) and Playwright.  Key capabilities:

- **BrowserManager** – lifecycle management for stealth browser instances,
  per-account isolated contexts, encrypted cookie persistence, and proxy routing.
- **ResourceBlocker** – route-level ad / tracker / fingerprint-service blocking.
- **SecureCookieStorage** – Fernet-encrypted on-disk cookie storage with key
  rotation support.
- **StealthHub** – JavaScript injection hub for canvas, WebGL, audio, and
  navigator property spoofing.
- **HumanProfile** – behavioral timing profiles (fast / normal / cautious /
  distracted) to vary interaction cadence.

Submodules:
    instance: ``BrowserManager`` class.
    blocker: ``ResourceBlocker`` route handler.
    secure_storage: ``SecureCookieStorage`` for encrypted cookie persistence.
    stealth_hub: ``StealthHub`` and ``HumanProfile`` anti-fingerprinting helpers.
    stealth_scripts: Raw JS payloads injected by ``StealthHub``.
"""

from .instance import BrowserManager

__all__ = ["BrowserManager"]
