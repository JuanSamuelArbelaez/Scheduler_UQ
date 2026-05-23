#!/usr/bin/env python3
"""
MCP Calendar Server Launcher
Starts the MCP server on the configured port
"""
import sys
import os

# Get the project root directory (parent of mcp_server)
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load environment variables from .env file manually
env_file = os.path.join(project_root, ".env")

if os.path.exists(env_file):
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if line and not line.startswith("#"):
                if "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()

# Add parent directory to path so we can import mcp_server
sys.path.insert(0, project_root)

from mcp_server.server import run_server

if __name__ == "__main__":
    host = "0.0.0.0"
    port = 8088
    service_account_file = None
    
    # Check environment variables
    if "MCP_HOST" in os.environ:
        host = os.environ["MCP_HOST"].strip() or "0.0.0.0"

    if "MCP_PORT" in os.environ:
        port = int(os.environ["MCP_PORT"])
    
    if "GOOGLE_SERVICE_ACCOUNT_FILE" in os.environ:
        service_account_file = os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"]
    
    run_server(host=host, port=port, service_account_file=service_account_file)
