# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Proxy Sticky Sessions**: Implemented logic to keep using the same proxy session for an account until it dies, reducing ban rates.
- **2Captcha Proxy Integration**: Added support for fetching and rotating residential proxies directly via 2Captcha API.
- **Win/Loss Analytics**: New `earnings_analytics.json` execution path to track every claim attempt.
- **Community Files**: Added `LICENSE`, `CONTRIBUTING.md`, and `CHANGELOG.md`.

### Changed

- **Deployment Script**: Unified `deploy.sh` to handle both local dev setup and Azure VM service installation.
- **Docs**: Professionalized `README.md` and consolidated documentation.
- **Config**: Moved hardcoded credentials and proxy configs to `.env`.

### Fixed

- **Proxy Rotation**: Fixed issue where dead proxies were being reused.
- **FireFaucet**: Resolved login timeout anomalies.
- **Azure Monitor**: Fixed path resolution for `faucet_worker.service`.

## [3.0.0] - 2026-01-15

### Initial Release (Gen 3.0)

- **Stealth**: Migrated to `Camoufox` for advanced anti-detection.
- **Architecture**: Modular `Faucets` class design.
- **Concurrency**: `JobScheduler` for parallel faucet running.
- **Solvers**: Integrated support for Turnstile, hCaptcha, and ReCaptcha V2.
