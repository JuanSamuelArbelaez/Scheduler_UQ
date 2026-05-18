"""
Integration tests for MCP server running with HTTP requests
"""
from __future__ import annotations

import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import HTTPServer

from mcp_server.server import (
    GoogleCalendarService,
    MCPCalendarHandler,
    MCPRPCRouter,
)


class MCPServerIntegrationTests(unittest.TestCase):
    """Test MCP server with actual HTTP requests"""

    server: HTTPServer | None = None
    server_thread: threading.Thread | None = None
    server_port: int = 18088

    @classmethod
    def setUpClass(cls) -> None:
        """Start MCP server in background"""
        calendar_service = GoogleCalendarService(service_account_file=None)
        MCPCalendarHandler.rpc_router = MCPRPCRouter(calendar_service)

        cls.server = HTTPServer(("localhost", cls.server_port), MCPCalendarHandler)
        
        def run_server() -> None:
            cls.server.handle_request()
        
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        
        # Give server time to start
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls) -> None:
        """Stop MCP server"""
        if cls.server:
            cls.server.shutdown()

    def test_server_responds_to_tools_list(self) -> None:
        """Test that server responds to tools/list request"""
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": None,
            "id": 1,
        }
        
        response = self._make_request(payload)
        
        self.assertIn("result", response)
        self.assertIn("tools", response["result"])
        tools = response["result"]["tools"]
        self.assertGreater(len(tools), 0)
        self.assertEqual(tools[0]["name"], "google_calendar.create_event")

    def test_server_responds_to_create_event(self) -> None:
        """Test creating an event via MCP"""
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "google_calendar.create_event",
                "arguments": {
                    "calendar_id": "test@example.com",
                    "title": "Test Event",
                    "start_time_utc": "2026-05-20T14:00:00Z",
                    "end_time_utc": "2026-05-20T15:00:00Z",
                },
            },
            "id": 2,
        }
        
        response = self._make_request(payload)
        
        self.assertIn("result", response)
        self.assertIn("external_id", response["result"])
        self.assertIsNotNone(response["result"]["external_id"])

    def test_server_responds_to_update_event(self) -> None:
        """Test updating an event via MCP"""
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "google_calendar.update_event",
                "arguments": {
                    "calendar_id": "test@example.com",
                    "event_id": "mock_123",
                    "title": "Updated Event",
                },
            },
            "id": 3,
        }
        
        response = self._make_request(payload)
        
        self.assertIn("result", response)
        self.assertEqual(response["result"]["external_id"], "mock_123")

    def test_server_responds_to_delete_event(self) -> None:
        """Test deleting an event via MCP"""
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "google_calendar.delete_event",
                "arguments": {
                    "calendar_id": "test@example.com",
                    "event_id": "mock_123",
                },
            },
            "id": 4,
        }
        
        response = self._make_request(payload)
        
        self.assertIn("result", response)
        self.assertEqual(response["result"]["external_id"], "mock_123")

    def test_server_handles_invalid_method(self) -> None:
        """Test server response to invalid method"""
        payload = {
            "jsonrpc": "2.0",
            "method": "invalid/method",
            "params": None,
            "id": 5,
        }
        
        response = self._make_request(payload)
        
        self.assertIn("error", response)
        self.assertEqual(response["error"]["code"], -32601)

    def _make_request(self, payload: dict) -> dict:
        """Make HTTP POST request to MCP server"""
        url = f"http://localhost:{self.server_port}/mcp"
        request_body = json.dumps(payload).encode("utf-8")
        
        request = urllib.request.Request(
            url,
            data=request_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            return json.loads(body)


if __name__ == "__main__":
    unittest.main()
