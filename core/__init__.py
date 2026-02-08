"""Core module for Cryptobot Gen 3.0.

This package contains the central orchestration, configuration,
analytics, proxy management, and monitoring components that power
the faucet automation system.

Submodules:
    config: Application settings via Pydantic.
    orchestrator: Priority-queue engine with error recovery.
    registry: Factory mapping faucet names to bot classes.
    analytics: Earnings tracking and profitability metrics.
    proxy_manager: Proxy pool with health scoring and rotation.
    wallet_manager: JSON-RPC interface to wallet daemons.
    extractor: Page-level timer and balance parsing.
    monitoring: Real-time Rich dashboard for faucet health.
    health_monitor: Service health checks and auto-restart.
    health_endpoint: HTTP server for ``/health`` and ``/metrics``.
    azure_monitor: OpenTelemetry / Azure Application Insights.
    auto_withdrawal: Withdrawal orchestration during off-peak.
    withdrawal_analytics: SQLite withdrawal transaction tracking.
    dashboard_builder: Profitability report builder (Rich).
    logging_setup: Compressed rotating file + console logging.
    utils: Corruption-safe JSON read/write helpers.
"""
