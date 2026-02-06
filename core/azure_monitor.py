"""
Azure Monitor OpenTelemetry Integration

Enterprise-grade monitoring for cryptobot using Azure Application Insights.
Uses the OpenTelemetry distro (recommended by Microsoft for Python apps in 2024+).
"""

import os
import json
import logging
import time
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from pathlib import Path

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


class MetricRetentionStore:
    """
    Stores metrics locally for 30-day retention and historical analysis.
    Complements Azure Monitor with local persistence.
    """
    
    RETENTION_DAYS = 30
    
    def __init__(self, storage_dir: Optional[Path] = None):
        """
        Initialize metric retention store.
        
        Args:
            storage_dir: Directory for storing metrics (default: config/metrics/)
        """
        if storage_dir is None:
            from core.config import CONFIG_DIR
            storage_dir = CONFIG_DIR / "metrics"
        
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.metrics_file = self.storage_dir / "retained_metrics.json"
        self.metrics: List[Dict[str, Any]] = []
        self._load_metrics()
    
    def _load_metrics(self):
        """Load metrics from disk."""
        try:
            if self.metrics_file.exists():
                with open(self.metrics_file, 'r') as f:
                    data = json.load(f)
                    # Only keep metrics within retention period
                    cutoff = time.time() - (self.RETENTION_DAYS * 86400)
                    self.metrics = [
                        m for m in data 
                        if m.get('timestamp', 0) > cutoff
                    ]
                logger.debug(f"Loaded {len(self.metrics)} retained metrics")
        except Exception as e:
            logger.debug(f"Could not load retained metrics: {e}")
            self.metrics = []
    
    def _save_metrics(self):
        """Save metrics to disk."""
        try:
            with open(self.metrics_file, 'w') as f:
                json.dump(self.metrics, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save retained metrics: {e}")
    
    def record_metric(self, name: str, value: float, tags: Optional[Dict[str, Any]] = None):
        """
        Record a metric with 30-day retention.
        
        Args:
            name: Metric name
            value: Metric value
            tags: Optional tags/metadata
        """
        metric = {
            'timestamp': time.time(),
            'name': name,
            'value': value,
            'tags': tags or {}
        }
        self.metrics.append(metric)
        
        # Cleanup old metrics periodically (every 100 records)
        if len(self.metrics) % 100 == 0:
            cutoff = time.time() - (self.RETENTION_DAYS * 86400)
            self.metrics = [m for m in self.metrics if m['timestamp'] > cutoff]
        
        self._save_metrics()
    
    def get_metrics(self, name: Optional[str] = None, hours: int = 24) -> List[Dict[str, Any]]:
        """
        Get metrics from the last N hours.
        
        Args:
            name: Optional metric name filter
            hours: Hours to look back
            
        Returns:
            List of metrics matching criteria
        """
        cutoff = time.time() - (hours * 3600)
        filtered = [m for m in self.metrics if m['timestamp'] > cutoff]
        
        if name:
            filtered = [m for m in filtered if m['name'] == name]
        
        return filtered
    
    def get_daily_summary(self, days: int = 1) -> Dict[str, Any]:
        """
        Get aggregated metrics summary for the last N days.
        
        Args:
            days: Number of days to summarize
            
        Returns:
            Dictionary with metric summaries
        """
        cutoff = time.time() - (days * 86400)
        recent = [m for m in self.metrics if m['timestamp'] > cutoff]
        
        summary = {
            'period_days': days,
            'total_metrics': len(recent),
            'metrics': {}
        }
        
        # Group by metric name
        by_name: Dict[str, List[float]] = {}
        for m in recent:
            name = m['name']
            if name not in by_name:
                by_name[name] = []
            by_name[name].append(m['value'])
        
        # Calculate statistics for each metric
        for name, values in by_name.items():
            summary['metrics'][name] = {
                'count': len(values),
                'avg': sum(values) / len(values) if values else 0,
                'min': min(values) if values else 0,
                'max': max(values) if values else 0,
                'latest': values[-1] if values else 0
            }
        
        return summary


# Global metric retention store
_metric_store: Optional[MetricRetentionStore] = None


def get_metric_store() -> MetricRetentionStore:
    """Get the global metric retention store."""
    global _metric_store
    if _metric_store is None:
        _metric_store = MetricRetentionStore()
    return _metric_store


def track_service_event(event_type: str, message: str, severity: str = "info"):
    """
    Track service lifecycle events (starts, stops, crashes, restarts).
    
    Args:
        event_type: Type of event (start, stop, crash, restart)
        message: Event message
        severity: Event severity (info, warning, error, critical)
    """
    if _tracer:
        try:
            with _tracer.start_as_current_span(f"service/{event_type}") as span:
                span.set_attribute("event.type", event_type)
                span.set_attribute("event.message", message)
                span.set_attribute("event.severity", severity)
                
                if severity in ("error", "critical"):
                    span.set_status(Status(StatusCode.ERROR, message))
                else:
                    span.set_status(Status(StatusCode.OK))
        except Exception as e:
            logger.debug(f"Failed to track service event: {e}")
    
    # Also store locally
    get_metric_store().record_metric(
        f"service.event.{event_type}",
        1.0,
        {'message': message, 'severity': severity}
    )
