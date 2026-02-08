"""
Core module for Cryptobot Gen 3.0.

This package contains the central orchestration, configuration, analytics,
proxy management, and monitoring components that power the faucet automation system.

Submodules:
    config: Application settings (``BotSettings``, ``AccountProfile``) via Pydantic.
    orchestrator: ``JobScheduler`` priority-queue engine with error recovery.
    registry: Factory registry mapping faucet names to bot classes.
    analytics: Earnings tracking, price feeds, and profitability metrics.
    proxy_manager: Residential proxy pool with health scoring and rotation.
    wallet_manager: JSON-RPC interface to Electrum / Bitcoin Core daemons.
    extractor: ``DataExtractor`` for page-level timer and balance parsing.
    monitoring: Real-time dashboard (Rich) for per-faucet health.
    health_monitor: Service-level health checks, alerts, and auto-restart.
    health_endpoint: Lightweight HTTP server exposing ``/health`` and ``/metrics``.
    azure_monitor: OpenTelemetry integration with Azure Application Insights.
    auto_withdrawal: Automated withdrawal orchestration during off-peak hours.
    withdrawal_analytics: SQLite-backed withdrawal transaction tracking.
    dashboard_builder: Profitability report builder with Rich panels.
    logging_setup: Compressed rotating file + safe console logging.
    utils: Corruption-safe JSON read/write helpers.
"""
