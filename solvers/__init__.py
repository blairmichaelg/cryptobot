"""
Solvers module for Cryptobot Gen 3.0.

Provides CAPTCHA solving and shortlink traversal capabilities used by faucet
bots during the claim workflow.

Submodules:
    captcha: ``CaptchaSolver`` – hybrid solver supporting 2Captcha, CapSolver,
        and manual human-in-the-loop modes.  Handles Turnstile, hCaptcha,
        reCAPTCHA v2/v3, and image CAPTCHAs with daily budget tracking and
        adaptive provider routing.
    capsolver: ``CapSolverClient`` – async API client for the CapSolver service.
    shortlink: ``ShortlinkSolver`` – generic multi-step shortlink traversal with
        timer detection, CAPTCHA solving, and redirect following.
"""
