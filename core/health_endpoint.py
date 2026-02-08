"""HTTP Health Endpoint for Cryptobot.

Provides a simple HTTP server that exposes health metrics for external
monitoring.  Can be consumed by uptime monitors, load balancers, or
container orchestrators.

Usage::

    python -m core.health_endpoint --port 8080

Endpoints:
    GET /health  -- Returns 200 if healthy, 503 if unhealthy.
    GET /metrics -- Returns detailed health metrics as JSON.
"""

import argparse
import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional

from core.health_monitor import HealthMonitor, HealthStatus

logger = logging.getLogger(__name__)


class HealthHandler(BaseHTTPRequestHandler):
    """HTTP request handler for health check endpoints."""

    # Class-level health monitor instance
    monitor: Optional[HealthMonitor] = None

    def do_GET(self) -> None:  # noqa: N802 -- required by BaseHTTPRequestHandler
        """Route incoming GET requests to the appropriate handler."""
        if self.path == '/health':
            self._handle_health()
        elif self.path == '/metrics':
            self._handle_metrics()
        elif self.path == '/':
            self._handle_index()
        else:
            self.send_error(404, "Not Found")

    def _handle_health(self) -> None:
        """Handle ``/health`` endpoint.

        Returns HTTP 200 when the system is healthy and HTTP 503
        otherwise.
        """
        try:
            result = self.monitor.perform_health_check()

            if result.status == HealthStatus.HEALTHY:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                response = {
                    'status': 'healthy',
                    'timestamp': result.timestamp,
                }
                self.wfile.write(
                    json.dumps(response).encode(),
                )
            else:
                self.send_response(503)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                response = {
                    'status': result.status.value.lower(),
                    'timestamp': result.timestamp,
                    'alerts': result.alerts,
                }
                self.wfile.write(
                    json.dumps(response).encode(),
                )

        except Exception as e:
            logger.error(
                "Health check error: %s", e, exc_info=True,
            )
            self.send_error(
                500, f"Health check failed: {e!s}",
            )

    def _handle_metrics(self) -> None:
        """Handle ``/metrics`` endpoint.

        Returns detailed health metrics as pretty-printed JSON.
        """
        try:
            result = self.monitor.perform_health_check()

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()

            response = result.to_dict()
            self.wfile.write(
                json.dumps(response, indent=2).encode(),
            )

        except Exception as e:
            logger.error(
                "Metrics error: %s", e, exc_info=True,
            )
            self.send_error(500, f"Metrics failed: {e!s}")

    def _handle_index(self) -> None:
        """Handle root endpoint -- render a simple HTML overview."""
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()

        html = (
            "<!DOCTYPE html>"
            "<html>"
            "<head>"
            "<title>Cryptobot Health Monitor</title>"
            "<style>"
            "body { font-family: Arial, sans-serif; margin: 40px; }"
            "h1 { color: #333; }"
            ".endpoint { background: #f4f4f4; padding: 10px; "
            "margin: 10px 0; border-radius: 5px; }"
            "code { background: #e0e0e0; padding: 2px 5px; "
            "border-radius: 3px; }"
            "</style>"
            "</head>"
            "<body>"
            "<h1>Cryptobot Health Monitor</h1>"
            "<p>Available endpoints:</p>"
            '<div class="endpoint">'
            "<strong>GET /health</strong><br>"
            "Simple health check. Returns 200 if healthy, "
            "503 if unhealthy."
            "</div>"
            '<div class="endpoint">'
            "<strong>GET /metrics</strong><br>"
            "Detailed health metrics as JSON including service "
            "status, resource usage, and alerts."
            "</div>"
            "<p>Example usage:</p>"
            "<code>curl http://localhost:8080/health</code><br>"
            "<code>curl http://localhost:8080/metrics</code>"
            "</body>"
            "</html>"
        )
        self.wfile.write(html.encode())

    def log_message(self, fmt: str, *args: object) -> None:
        """Override to route HTTP log messages through Python logging.

        Args:
            fmt: ``printf``-style format string.
            *args: Positional arguments for *fmt*.
        """
        logger.info(
            "%s - %s", self.address_string(), fmt % args,
        )


def run_server(
    port: int = 8080, host: str = '0.0.0.0',
) -> None:
    """Start the health endpoint HTTP server.

    Args:
        port: Port to listen on (default ``8080``).
        host: Host to bind to (default ``0.0.0.0``).
    """
    # Create health monitor instance
    HealthHandler.monitor = HealthMonitor()

    # Create and start server
    server_address = (host, port)
    httpd = HTTPServer(server_address, HealthHandler)

    logger.info(
        "Starting health endpoint server on %s:%d", host, port,
    )
    logger.info("Health check: http://%s:%d/health", host, port)
    logger.info("Metrics: http://%s:%d/metrics", host, port)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        httpd.shutdown()


def main() -> None:
    """CLI entry point for the health endpoint server."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    )

    parser = argparse.ArgumentParser(
        description="Cryptobot Health Endpoint Server",
    )
    parser.add_argument(
        '--port',
        type=int,
        default=8080,
        help='Port to listen on (default: 8080)',
    )
    parser.add_argument(
        '--host',
        type=str,
        default='0.0.0.0',
        help='Host to bind to (default: 0.0.0.0)',
    )

    args = parser.parse_args()

    run_server(port=args.port, host=args.host)


if __name__ == "__main__":
    main()
