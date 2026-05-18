#!/usr/bin/env python3
"""
MCP Calendar Server Launcher
Starts the MCP server on the configured port
"""
import sys
import os

# Add parent directory to path so we can import mcp_server
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_server.server import run_server

if __name__ == "__main__":
    port = 8088
    service_account_file = None
    
    # Check environment variables
    if "MCP_PORT" in os.environ:
        port = int(os.environ["MCP_PORT"])
    
    if "GOOGLE_SERVICE_ACCOUNT_FILE" in os.environ:
        service_account_file = os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"]
    
    print(f"Starting MCP Calendar Server on port {port}")
    print(f"Service account file: {service_account_file or 'None (mock mode)'}")
    
    run_server(port=port, service_account_file=service_account_file)
