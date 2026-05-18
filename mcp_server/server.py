"""
MCP Server for Google Calendar Integration
Handles calendar event synchronization via JSON-RPC over HTTP
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
import logging
import os
from typing import Any
from http.server import BaseHTTPRequestHandler, HTTPServer
import base64

from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
import dateutil.parser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MCPRequest:
    jsonrpc: str
    method: str
    params: dict[str, Any] | None
    id: int | str


@dataclass(slots=True)
class MCPResponse:
    jsonrpc: str = "2.0"
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    id: int | str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {"jsonrpc": self.jsonrpc}
        if self.result is not None:
            data["result"] = self.result
        if self.error is not None:
            data["error"] = self.error
        if self.id is not None:
            data["id"] = self.id
        return data


class GoogleCalendarService:
    """Wrapper around Google Calendar API"""

    def __init__(self, service_account_file: str | None = None) -> None:
        self.service = None
        self.initialized = False
        
        if service_account_file and os.path.exists(service_account_file):
            try:
                credentials = service_account.Credentials.from_service_account_file(
                    service_account_file,
                    scopes=["https://www.googleapis.com/auth/calendar"]
                )
                self.service = build("calendar", "v3", credentials=credentials)
                self.initialized = True
                logger.info("Google Calendar service initialized with service account")
            except Exception as e:
                logger.warning(f"Failed to initialize with service account: {e}")
        
        # Fallback: use environment variable or mock mode
        if not self.initialized:
            logger.info("Running in mock mode (no real Google Calendar API)")
            self.initialized = True

    def is_mock(self) -> bool:
        return self.service is None

    def create_event(
        self,
        calendar_id: str,
        title: str,
        start_time_utc: str,
        end_time_utc: str,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a calendar event"""
        if self.is_mock():
            event_id = f"mock_{datetime.now().timestamp()}"
            logger.info(f"Mock: Created event {event_id} in calendar {calendar_id}")
            return {
                "id": event_id,
                "summary": title,
                "start": {"dateTime": start_time_utc},
                "end": {"dateTime": end_time_utc},
                "description": description,
                "location": location,
                "organizer": {"email": calendar_id},
            }

        try:
            body = {
                "summary": title,
                "start": {"dateTime": start_time_utc},
                "end": {"dateTime": end_time_utc},
            }
            if description:
                body["description"] = description
            if location:
                body["location"] = location
            if attendees:
                body["attendees"] = [{"email": email} for email in attendees]

            event = self.service.events().insert(calendarId=calendar_id, body=body).execute()
            logger.info(f"Created Google Calendar event: {event.get('id')}")
            return event
        except Exception as e:
            logger.error(f"Failed to create event: {e}")
            raise

    def update_event(
        self,
        calendar_id: str,
        event_id: str,
        title: str | None = None,
        start_time_utc: str | None = None,
        end_time_utc: str | None = None,
        description: str | None = None,
        location: str | None = None,
    ) -> dict[str, Any]:
        """Update a calendar event"""
        if self.is_mock():
            logger.info(f"Mock: Updated event {event_id} in calendar {calendar_id}")
            return {"id": event_id, "summary": title, "updated": True}

        try:
            event = self.service.events().get(calendarId=calendar_id, eventId=event_id).execute()
            
            if title:
                event["summary"] = title
            if start_time_utc:
                event["start"] = {"dateTime": start_time_utc}
            if end_time_utc:
                event["end"] = {"dateTime": end_time_utc}
            if description:
                event["description"] = description
            if location:
                event["location"] = location

            updated_event = self.service.events().update(
                calendarId=calendar_id, eventId=event_id, body=event
            ).execute()
            logger.info(f"Updated Google Calendar event: {event_id}")
            return updated_event
        except Exception as e:
            logger.error(f"Failed to update event: {e}")
            raise

    def delete_event(self, calendar_id: str, event_id: str) -> bool:
        """Delete a calendar event"""
        if self.is_mock():
            logger.info(f"Mock: Deleted event {event_id} from calendar {calendar_id}")
            return True

        try:
            self.service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
            logger.info(f"Deleted Google Calendar event: {event_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete event: {e}")
            raise

    def list_events(
        self, calendar_id: str, max_results: int = 10
    ) -> list[dict[str, Any]]:
        """List calendar events"""
        if self.is_mock():
            logger.info(f"Mock: Listed events from calendar {calendar_id}")
            return []

        try:
            events_result = (
                self.service.events()
                .list(
                    calendarId=calendar_id,
                    maxResults=max_results,
                    orderBy="startTime",
                    singleEvents=True,
                )
                .execute()
            )
            return events_result.get("items", [])
        except Exception as e:
            logger.error(f"Failed to list events: {e}")
            return []


class MCPRPCRouter:
    """Routes JSON-RPC method calls for MCP calendar"""

    def __init__(self, calendar_service: GoogleCalendarService | None = None) -> None:
        self.calendar_service = calendar_service

    def handle_rpc_method(self, request: MCPRequest) -> MCPResponse:
        """Route JSON-RPC method calls"""
        method = request.method
        params = request.params or {}

        if method == "tools/list":
            return MCPResponse(
                result={
                    "tools": [
                        {
                            "name": "google_calendar.create_event",
                            "description": "Create a new Google Calendar event",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "calendar_id": {"type": "string"},
                                    "title": {"type": "string"},
                                    "start_time_utc": {"type": "string"},
                                    "end_time_utc": {"type": "string"},
                                    "description": {"type": "string"},
                                    "location": {"type": "string"},
                                },
                                "required": ["calendar_id", "title", "start_time_utc", "end_time_utc"],
                            },
                        },
                        {
                            "name": "google_calendar.update_event",
                            "description": "Update a Google Calendar event",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "calendar_id": {"type": "string"},
                                    "event_id": {"type": "string"},
                                    "title": {"type": "string"},
                                    "start_time_utc": {"type": "string"},
                                    "end_time_utc": {"type": "string"},
                                    "description": {"type": "string"},
                                    "location": {"type": "string"},
                                },
                                "required": ["calendar_id", "event_id"],
                            },
                        },
                        {
                            "name": "google_calendar.delete_event",
                            "description": "Delete a Google Calendar event",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "calendar_id": {"type": "string"},
                                    "event_id": {"type": "string"},
                                },
                                "required": ["calendar_id", "event_id"],
                            },
                        },
                    ]
                },
                id=request.id,
            )

        elif method == "prompts/list":
            return MCPResponse(
                result={
                    "prompts": [
                        {
                            "name": "calendar-event-template",
                            "description": "Template for creating calendar events",
                        }
                    ]
                },
                id=request.id,
            )

        elif method == "resources/list":
            return MCPResponse(
                result={
                    "resources": [
                        {
                            "uri": "google-calendar://primary",
                            "name": "Primary Calendar",
                            "description": "User's primary Google Calendar",
                        }
                    ]
                },
                id=request.id,
            )

        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            
            if tool_name == "google_calendar.create_event":
                return self.call_create_event(arguments, request.id)
            elif tool_name == "google_calendar.update_event":
                return self.call_update_event(arguments, request.id)
            elif tool_name == "google_calendar.delete_event":
                return self.call_delete_event(arguments, request.id)
            else:
                return MCPResponse(
                    error={"code": -32601, "message": f"Method not found: {tool_name}"},
                    id=request.id,
                )

        else:
            return MCPResponse(
                error={"code": -32601, "message": f"Method not found: {method}"},
                id=request.id,
            )

    def call_create_event(
        self, arguments: dict[str, Any], request_id: int | str | None
    ) -> MCPResponse:
        """Handle google_calendar.create_event"""
        try:
            calendar_id = arguments.get("calendar_id", "primary")
            title = arguments.get("title", "Untitled")
            start_time_utc = arguments.get("start_time_utc", "")
            end_time_utc = arguments.get("end_time_utc", "")
            description = arguments.get("description")
            location = arguments.get("location")

            if not self.calendar_service:
                raise RuntimeError("Calendar service not initialized")

            event = self.calendar_service.create_event(
                calendar_id=calendar_id,
                title=title,
                start_time_utc=start_time_utc,
                end_time_utc=end_time_utc,
                description=description,
                location=location,
            )

            return MCPResponse(
                result={
                    "content": [{"type": "text", "text": f"Event created: {event.get('id')}"}],
                    "external_id": event.get("id"),
                },
                id=request_id,
            )
        except Exception as e:
            logger.error(f"Error in create_event: {e}")
            return MCPResponse(
                error={"code": -32603, "message": str(e)},
                id=request_id,
            )

    def call_update_event(
        self, arguments: dict[str, Any], request_id: int | str | None
    ) -> MCPResponse:
        """Handle google_calendar.update_event"""
        try:
            calendar_id = arguments.get("calendar_id", "primary")
            event_id = arguments.get("event_id", "")
            title = arguments.get("title")
            start_time_utc = arguments.get("start_time_utc")
            end_time_utc = arguments.get("end_time_utc")
            description = arguments.get("description")
            location = arguments.get("location")

            if not event_id:
                raise ValueError("event_id is required")

            if not self.calendar_service:
                raise RuntimeError("Calendar service not initialized")

            event = self.calendar_service.update_event(
                calendar_id=calendar_id,
                event_id=event_id,
                title=title,
                start_time_utc=start_time_utc,
                end_time_utc=end_time_utc,
                description=description,
                location=location,
            )

            return MCPResponse(
                result={
                    "content": [{"type": "text", "text": f"Event updated: {event.get('id')}"}],
                    "external_id": event.get("id"),
                },
                id=request_id,
            )
        except Exception as e:
            logger.error(f"Error in update_event: {e}")
            return MCPResponse(
                error={"code": -32603, "message": str(e)},
                id=request_id,
            )

    def call_delete_event(
        self, arguments: dict[str, Any], request_id: int | str | None
    ) -> MCPResponse:
        """Handle google_calendar.delete_event"""
        try:
            calendar_id = arguments.get("calendar_id", "primary")
            event_id = arguments.get("event_id", "")

            if not event_id:
                raise ValueError("event_id is required")

            if not self.calendar_service:
                raise RuntimeError("Calendar service not initialized")

            success = self.calendar_service.delete_event(
                calendar_id=calendar_id,
                event_id=event_id,
            )

            return MCPResponse(
                result={
                    "content": [{"type": "text", "text": f"Event deleted: {event_id}"}],
                    "external_id": event_id,
                },
                id=request_id,
            )
        except Exception as e:
            logger.error(f"Error in delete_event: {e}")
            return MCPResponse(
                error={"code": -32603, "message": str(e)},
                id=request_id,
            )



class MCPCalendarHandler(BaseHTTPRequestHandler):
    """HTTP request handler for MCP calendar operations"""

    rpc_router: MCPRPCRouter | None = None

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default logging"""
        logger.info(f"{self.client_address[0]} - {format % args}")

    def do_POST(self) -> None:
        """Handle POST requests (JSON-RPC)"""
        if self.path != "/mcp":
            self.send_error(404, "Not Found")
            return

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length).decode("utf-8")
            request_data = json.loads(raw_body)
        except Exception as e:
            self.send_json_response(
                MCPResponse(
                    error={"code": -32700, "message": "Parse error"},
                    id=None,
                )
            )
            return

        try:
            mcp_request = MCPRequest(
                jsonrpc=request_data.get("jsonrpc", "2.0"),
                method=request_data.get("method", ""),
                params=request_data.get("params"),
                id=request_data.get("id"),
            )

            if not self.rpc_router:
                raise RuntimeError("RPC router not initialized")

            response = self.rpc_router.handle_rpc_method(mcp_request)
        except Exception as e:
            logger.error(f"Unhandled error: {e}")
            response = MCPResponse(
                error={"code": -32603, "message": f"Internal error: {e}"},
                id=mcp_request.id if "mcp_request" in locals() else None,
            )

        self.send_json_response(response)

    def send_json_response(self, response: MCPResponse) -> None:
        """Send JSON response"""
        response_data = response.to_dict()
        response_body = json.dumps(response_data, ensure_ascii=False).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(response_body))
        self.end_headers()
        self.wfile.write(response_body)


def run_server(
    host: str = "localhost",
    port: int = 8088,
    service_account_file: str | None = None,
) -> None:
    """Run the MCP server"""
    logger.info(f"Starting MCP Calendar Server on {host}:{port}")
    
    # Initialize calendar service and RPC router
    calendar_service = GoogleCalendarService(service_account_file)
    MCPCalendarHandler.rpc_router = MCPRPCRouter(calendar_service)
    
    if calendar_service.is_mock():
        logger.warning("Running in MOCK mode - no real Google Calendar sync")
    else:
        logger.info("Connected to real Google Calendar API")

    server = HTTPServer((host, port), MCPCalendarHandler)
    logger.info(f"MCP server listening on http://{host}:{port}/mcp")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down MCP server")
        server.shutdown()


if __name__ == "__main__":
    import sys
    
    port = 8088
    service_account_file = None
    
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    if len(sys.argv) > 2:
        service_account_file = sys.argv[2]
    
    run_server(port=port, service_account_file=service_account_file)
