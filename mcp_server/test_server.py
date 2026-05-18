"""
Tests for MCP Calendar Server
"""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch, MagicMock
import urllib.request
import urllib.error
import threading
import time

from mcp_server.server import (
    GoogleCalendarService,
    MCPRPCRouter,
    MCPCalendarHandler,
    MCPRequest,
    MCPResponse,
    run_server,
)


class MCPServerTests(unittest.TestCase):
    """Test MCP server functionality"""

    def test_mcp_request_parsing(self) -> None:
        """Test parsing MCP requests"""
        request = MCPRequest(
            jsonrpc="2.0",
            method="tools/list",
            params=None,
            id=1,
        )
        self.assertEqual(request.method, "tools/list")
        self.assertEqual(request.id, 1)

    def test_mcp_response_generation(self) -> None:
        """Test generating MCP responses"""
        response = MCPResponse(
            result={"tools": [{"name": "test"}]},
            id=1,
        )
        data = response.to_dict()
        self.assertEqual(data["jsonrpc"], "2.0")
        self.assertEqual(data["id"], 1)
        self.assertIn("tools", data["result"])

    def test_mcp_error_response(self) -> None:
        """Test MCP error responses"""
        response = MCPResponse(
            error={"code": -32601, "message": "Method not found"},
            id=2,
        )
        data = response.to_dict()
        self.assertIsNotNone(data["error"])
        self.assertIsNone(data.get("result"))

    def test_google_calendar_service_mock_mode(self) -> None:
        """Test Google Calendar service in mock mode"""
        service = GoogleCalendarService(service_account_file=None)
        self.assertTrue(service.is_mock())

        event = service.create_event(
            calendar_id="test@example.com",
            title="Test Event",
            start_time_utc="2026-05-20T14:00:00Z",
            end_time_utc="2026-05-20T15:00:00Z",
        )
        self.assertIsNotNone(event["id"])
        self.assertEqual(event["summary"], "Test Event")

    def test_google_calendar_update_mock(self) -> None:
        """Test updating events in mock mode"""
        service = GoogleCalendarService(service_account_file=None)
        
        event = service.update_event(
            calendar_id="test@example.com",
            event_id="mock_123",
            title="Updated Title",
        )
        self.assertEqual(event["id"], "mock_123")
        self.assertTrue(event.get("updated"))

    def test_google_calendar_delete_mock(self) -> None:
        """Test deleting events in mock mode"""
        service = GoogleCalendarService(service_account_file=None)
        
        result = service.delete_event(
            calendar_id="test@example.com",
            event_id="mock_123",
        )
        self.assertTrue(result)

    def test_mcp_handler_tools_list(self) -> None:
        """Test tools/list method"""
        router = MCPRPCRouter(GoogleCalendarService(service_account_file=None))
        
        request = MCPRequest(
            jsonrpc="2.0",
            method="tools/list",
            params=None,
            id=1,
        )
        response = router.handle_rpc_method(request)
        
        self.assertIsNone(response.error)
        self.assertIsNotNone(response.result)
        self.assertIn("tools", response.result)
        tools = response.result["tools"]
        tool_names = [t["name"] for t in tools]
        self.assertIn("google_calendar.create_event", tool_names)
        self.assertIn("google_calendar.update_event", tool_names)
        self.assertIn("google_calendar.delete_event", tool_names)

    def test_mcp_handler_prompts_list(self) -> None:
        """Test prompts/list method"""
        router = MCPRPCRouter(GoogleCalendarService(service_account_file=None))
        
        request = MCPRequest(
            jsonrpc="2.0",
            method="prompts/list",
            params=None,
            id=1,
        )
        response = router.handle_rpc_method(request)
        
        self.assertIsNone(response.error)
        self.assertIsNotNone(response.result)
        self.assertIn("prompts", response.result)

    def test_mcp_handler_resources_list(self) -> None:
        """Test resources/list method"""
        router = MCPRPCRouter(GoogleCalendarService(service_account_file=None))
        
        request = MCPRequest(
            jsonrpc="2.0",
            method="resources/list",
            params=None,
            id=1,
        )
        response = router.handle_rpc_method(request)
        
        self.assertIsNone(response.error)
        self.assertIsNotNone(response.result)
        self.assertIn("resources", response.result)

    def test_mcp_handler_unknown_method(self) -> None:
        """Test unknown method error"""
        router = MCPRPCRouter(GoogleCalendarService(service_account_file=None))
        
        request = MCPRequest(
            jsonrpc="2.0",
            method="unknown/method",
            params=None,
            id=1,
        )
        response = router.handle_rpc_method(request)
        
        self.assertIsNotNone(response.error)
        self.assertEqual(response.error["code"], -32601)

    def test_create_event_tool_call(self) -> None:
        """Test calling create_event tool"""
        router = MCPRPCRouter(GoogleCalendarService(service_account_file=None))
        
        arguments = {
            "calendar_id": "test@example.com",
            "title": "Test Meeting",
            "start_time_utc": "2026-05-20T14:00:00Z",
            "end_time_utc": "2026-05-20T15:00:00Z",
            "description": "A test meeting",
        }
        response = router.call_create_event(arguments, request_id=1)
        
        self.assertIsNone(response.error)
        self.assertIsNotNone(response.result)
        self.assertIn("external_id", response.result)
        self.assertIn("content", response.result)

    def test_update_event_tool_call(self) -> None:
        """Test calling update_event tool"""
        router = MCPRPCRouter(GoogleCalendarService(service_account_file=None))
        
        arguments = {
            "calendar_id": "test@example.com",
            "event_id": "mock_123",
            "title": "Updated Meeting",
        }
        response = router.call_update_event(arguments, request_id=2)
        
        self.assertIsNone(response.error)
        self.assertIsNotNone(response.result)
        self.assertEqual(response.result["external_id"], "mock_123")

    def test_delete_event_tool_call(self) -> None:
        """Test calling delete_event tool"""
        router = MCPRPCRouter(GoogleCalendarService(service_account_file=None))
        
        arguments = {
            "calendar_id": "test@example.com",
            "event_id": "mock_123",
        }
        response = router.call_delete_event(arguments, request_id=3)
        
        self.assertIsNone(response.error)
        self.assertIsNotNone(response.result)
        self.assertEqual(response.result["external_id"], "mock_123")


if __name__ == "__main__":
    unittest.main()
