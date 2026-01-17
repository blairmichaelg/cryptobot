"""
Azure Monitor OpenTelemetry Integration

Enterprise-grade monitoring for cryptobot using Azure Application Insights.
Uses the OpenTelemetry distro (recommended by Microsoft for Python apps in 2024+).
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Flag to indicate if Azure Monitor is available
_azure_monitor_available = False
_tracer = None

try:
    from azure.monitor.opentelemetry import configure_azure_monitor
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    _azure_monitor_available = True
except ImportError:
    logger.debug("Azure Monitor OpenTelemetry not installed. Run: pip install azure-monitor-opentelemetry")


def initialize_azure_monitor(connection_string: Optional[str] = None) -> bool:
    """
    Initialize Azure Application Insights monitoring.
    
    Args:
        connection_string: Azure Application Insights connection string.
                          If not provided, reads from APPLICATIONINSIGHTS_CONNECTION_STRING env var.
    
    Returns:
        True if initialized successfully, False otherwise.
    """
    global _tracer, _azure_monitor_available
    
    if not _azure_monitor_available:
        logger.warning("Azure Monitor SDK not installed. Monitoring disabled.")
        return False
    
    conn_str = connection_string or os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    
    if not conn_str:
        logger.info("No Azure App Insights connection string. Monitoring disabled.")
        return False
    
    try:
        configure_azure_monitor(connection_string=conn_str)
        _tracer = trace.get_tracer(__name__)
        logger.info("✅ Azure Application Insights monitoring enabled")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize Azure Monitor: {e}")
        return False


def track_claim(faucet_name: str, success: bool, amount: float = 0, currency: str = "unknown"):
    """
    Track a claim event in Azure Application Insights.
    
    Args:
        faucet_name: Name of the faucet
        success: Whether the claim succeeded
        amount: Amount claimed
        currency: Currency code
    """
    if not _tracer:
        return
    
    try:
        with _tracer.start_as_current_span(f"claim/{faucet_name}") as span:
            span.set_attribute("faucet.name", faucet_name)
            span.set_attribute("claim.success", success)
            span.set_attribute("claim.amount", amount)
            span.set_attribute("claim.currency", currency)
            
            if success:
                span.set_status(Status(StatusCode.OK))
            else:
                span.set_status(Status(StatusCode.ERROR, "Claim failed"))
    except Exception as e:
        logger.debug(f"Failed to track claim: {e}")


def track_error(error_type: str, message: str, faucet_name: str = "unknown"):
    """
    Track an error event in Azure Application Insights.
    
    Args:
        error_type: Type of error (e.g., "proxy_detected", "login_failed")
        message: Error message
        faucet_name: Faucet where error occurred
    """
    if not _tracer:
        return
    
    try:
        with _tracer.start_as_current_span(f"error/{error_type}") as span:
            span.set_attribute("error.type", error_type)
            span.set_attribute("error.message", message)
            span.set_attribute("faucet.name", faucet_name)
            span.set_status(Status(StatusCode.ERROR, message))
    except Exception as e:
        logger.debug(f"Failed to track error: {e}")


def track_metric(name: str, value: float, tags: dict = None):
    """
    Track a custom metric in Azure Application Insights.
    
    Args:
        name: Metric name
        value: Metric value
        tags: Optional dictionary of tags
    """
    if not _tracer:
        return
    
    try:
        with _tracer.start_as_current_span(f"metric/{name}") as span:
            span.set_attribute("metric.name", name)
            span.set_attribute("metric.value", value)
            if tags:
                for key, val in tags.items():
                    span.set_attribute(f"metric.{key}", val)
    except Exception as e:
        logger.debug(f"Failed to track metric: {e}")
