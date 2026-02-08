"""Azure Monitor OpenTelemetry Integration.

Enterprise-grade monitoring for cryptobot using Azure Application Insights.
Uses the OpenTelemetry distro (recommended by Microsoft for Python apps
in 2024+).
"""

import os
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Module-level state for Azure Monitor integration.
# These are intentionally mutable; set once during initialisation.
_AZURE_MONITOR_AVAILABLE: bool = False
_TRACER: Optional[Any] = None

try:
    from azure.monitor.opentelemetry import configure_azure_monitor
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    _AZURE_MONITOR_AVAILABLE = True
except ImportError:
    logger.debug(
        "Azure Monitor OpenTelemetry not installed. "
        "Run: pip install azure-monitor-opentelemetry"
    )


def initialize_azure_monitor(
    connection_string: Optional[str] = None,
) -> bool:
    """Initialize Azure Application Insights monitoring.

    Args:
        connection_string: Azure Application Insights connection
            string.  If not provided, reads from the
            ``APPLICATIONINSIGHTS_CONNECTION_STRING`` env var.

    Returns:
        ``True`` if initialised successfully, ``False`` otherwise.
    """
    global _TRACER  # noqa: PLW0603

    if not _AZURE_MONITOR_AVAILABLE:
        logger.warning(
            "Azure Monitor SDK not installed. Monitoring disabled.",
        )
        return False

    conn_str = connection_string or os.environ.get(
        "APPLICATIONINSIGHTS_CONNECTION_STRING",
    )

    if not conn_str:
        logger.info(
            "No Azure App Insights connection string. "
            "Monitoring disabled.",
        )
        return False

    try:
        configure_azure_monitor(connection_string=conn_str)
        _TRACER = trace.get_tracer(__name__)
        logger.info(
            "Azure Application Insights monitoring enabled",
        )
        return True
    except Exception as e:
        logger.error(
            "Failed to initialize Azure Monitor: %s", e,
        )
        return False


def track_claim(
    faucet_name: str,
    success: bool,
    amount: float = 0,
    currency: str = "unknown",
) -> None:
    """Track a faucet claim event in Application Insights.

    Args:
        faucet_name: Name of the faucet.
        success: Whether the claim succeeded.
        amount: Amount claimed (smallest unit).
        currency: Currency code.
    """
    if not _TRACER:
        return

    try:
        with _TRACER.start_as_current_span(
            f"claim/{faucet_name}",
        ) as span:
            span.set_attribute("faucet.name", faucet_name)
            span.set_attribute("claim.success", success)
            span.set_attribute("claim.amount", amount)
            span.set_attribute("claim.currency", currency)

            if success:
                span.set_status(Status(StatusCode.OK))
            else:
                span.set_status(
                    Status(StatusCode.ERROR, "Claim failed"),
                )
    except Exception as e:
        logger.debug("Failed to track claim: %s", e)


def track_error(
    error_type: str,
    message: str,
    faucet_name: str = "unknown",
) -> None:
    """Track an error event in Application Insights.

    Args:
        error_type: Error category (e.g. ``"proxy_detected"``).
        message: Human-readable error message.
        faucet_name: Faucet where the error occurred.
    """
    if not _TRACER:
        return

    try:
        with _TRACER.start_as_current_span(
            f"error/{error_type}",
        ) as span:
            span.set_attribute("error.type", error_type)
            span.set_attribute("error.message", message)
            span.set_attribute("faucet.name", faucet_name)
            span.set_status(Status(StatusCode.ERROR, message))
    except Exception as e:
        logger.debug("Failed to track error: %s", e)


def track_metric(
    name: str,
    value: float,
    tags: Optional[Dict[str, Any]] = None,
) -> None:
    """Track a custom metric in Application Insights.

    Args:
        name: Metric name.
        value: Metric value.
        tags: Optional dictionary of tags to attach.
    """
    if not _TRACER:
        return

    try:
        with _TRACER.start_as_current_span(
            f"metric/{name}",
        ) as span:
            span.set_attribute("metric.name", name)
            span.set_attribute("metric.value", value)
            if tags:
                for key, val in tags.items():
                    span.set_attribute(f"metric.{key}", val)
    except Exception as e:
        logger.debug("Failed to track metric: %s", e)
