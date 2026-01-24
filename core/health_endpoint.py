"""
HTTP Health Endpoint for Cryptobot

Provides a simple HTTP server that exposes health metrics for external monitoring.
This can be used by uptime monitors, load balancers, or monitoring systems.

Usage:
    python -m core.health_endpoint --port 8080
    
Endpoints:
    GET /health - Returns 200 if healthy, 503 if unhealthy
    GET /metrics - Returns detailed health metrics as JSON
"""

import os
import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional

from core.health_monitor import HealthMonitor, HealthStatus

logger = logging.getLogger(__name__)


class HealthHandler(BaseHTTPRequestHandler):
    """HTTP request handler for health endpoints"""
    
    # Class-level health monitor instance
    monitor: Optional[HealthMonitor] = None
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/health':
            self.handle_health()
        elif self.path == '/metrics':
            self.handle_metrics()
        elif self.path == '/':
            self.handle_index()
        else:
            self.send_error(404, "Not Found")
    
    def handle_health(self):
        """
        Handle /health endpoint
        Returns 200 if healthy, 503 if unhealthy
        """
        try:
            result = self.monitor.perform_health_check()
            
            if result.status == HealthStatus.HEALTHY:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                response = {
                    'status': 'healthy',
                    'timestamp': result.timestamp
                }
                self.wfile.write(json.dumps(response).encode())
            else:
                self.send_response(503)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                response = {
                    'status': result.status.value.lower(),
                    'timestamp': result.timestamp,
                    'alerts': result.alerts
                }
                self.wfile.write(json.dumps(response).encode())
                
        except Exception as e:
            logger.error(f"Health check error: {e}", exc_info=True)
            self.send_error(500, f"Health check failed: {str(e)}")
    
    def handle_metrics(self):
        """
        Handle /metrics endpoint
        Returns detailed health metrics as JSON
        """
        try:
            result = self.monitor.perform_health_check()
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            response = result.to_dict()
            self.wfile.write(json.dumps(response, indent=2).encode())
            
        except Exception as e:
            logger.error(f"Metrics error: {e}", exc_info=True)
            self.send_error(500, f"Metrics failed: {str(e)}")
    
    def handle_index(self):
        """Handle root endpoint - return simple HTML page"""
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Cryptobot Health Monitor</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; }
                h1 { color: #333; }
                .endpoint { 
                    background: #f4f4f4; 
                    padding: 10px; 
                    margin: 10px 0; 
                    border-radius: 5px;
                }
                code { 
                    background: #e0e0e0; 
                    padding: 2px 5px; 
                    border-radius: 3px;
                }
            </style>
        </head>
        <body>
            <h1>Cryptobot Health Monitor</h1>
            <p>Available endpoints:</p>
            
            <div class="endpoint">
                <strong>GET /health</strong><br>
                Simple health check. Returns 200 if healthy, 503 if unhealthy.
            </div>
            
            <div class="endpoint">
                <strong>GET /metrics</strong><br>
                Detailed health metrics as JSON including service status, resource usage, and alerts.
            </div>
            
            <p>Example usage:</p>
            <code>curl http://localhost:8080/health</code><br>
            <code>curl http://localhost:8080/metrics</code>
        </body>
        </html>
        """
        self.wfile.write(html.encode())
    
    def log_message(self, format, *args):
        """Override to use Python logging instead of stderr"""
        logger.info(f"{self.address_string()} - {format % args}")


def run_server(port: int = 8080, host: str = '0.0.0.0'):
    """
    Run the health endpoint HTTP server
    
    Args:
        port: Port to listen on (default: 8080)
        host: Host to bind to (default: 0.0.0.0 for all interfaces)
    """
    # Create health monitor instance
    HealthHandler.monitor = HealthMonitor()
    
    # Create and start server
    server_address = (host, port)
    httpd = HTTPServer(server_address, HealthHandler)
    
    logger.info(f"Starting health endpoint server on {host}:{port}")
    logger.info(f"Health check: http://{host}:{port}/health")
    logger.info(f"Metrics: http://{host}:{port}/metrics")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        httpd.shutdown()


def main():
    """Main entry point for health endpoint server"""
    import argparse
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    parser = argparse.ArgumentParser(description="Cryptobot Health Endpoint Server")
    parser.add_argument(
        '--port',
        type=int,
        default=8080,
        help='Port to listen on (default: 8080)'
    )
    parser.add_argument(
        '--host',
        type=str,
        default='0.0.0.0',
        help='Host to bind to (default: 0.0.0.0)'
    )
    
    args = parser.parse_args()
    
    run_server(port=args.port, host=args.host)


if __name__ == "__main__":
    main()
