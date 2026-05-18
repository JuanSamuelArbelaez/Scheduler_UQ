from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
import json
import logging
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from models.entities import Event, User

from .calendar_provider import CalendarCapabilitySnapshot, CalendarProvider, CalendarSyncResult, CalendarTransport


logger = logging.getLogger(__name__)


class MCPTransportError(RuntimeError):
    pass


@dataclass(slots=True)
class MCPToolSpec:
    name: str
    description: str | None = None


class HttpJsonRpcMCPTransport(CalendarTransport):
    def __init__(self, endpoint: str, timeout_seconds: int = 15) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._request_id = 0

    def is_available(self) -> bool:
        try:
            self.list_tools()
            return True
        except Exception:
            return False

    def list_tools(self) -> dict[str, Any]:
        return self._request("tools/list")

    def list_templates(self) -> dict[str, Any]:
        return self._request("prompts/list")

    def list_resources(self) -> dict[str, Any]:
        return self._request("resources/list")

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._request("tools/call", {"name": tool_name, "arguments": arguments})

    def _request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._request_id += 1
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": self._request_id, "method": method}
        if params is not None:
            payload["params"] = params

        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except (URLError, TimeoutError, OSError) as error:
            raise MCPTransportError(str(error)) from error

        try:
            response_data = json.loads(raw_body)
        except json.JSONDecodeError as error:
            raise MCPTransportError("MCP response is not valid JSON") from error

        if isinstance(response_data, dict) and response_data.get("error"):
            raise MCPTransportError(str(response_data["error"]))
        if not isinstance(response_data, dict):
            raise MCPTransportError("MCP response must be a JSON object")

        result = response_data.get("result")
        return result if isinstance(result, dict) else response_data


class MCPCalendarProvider(CalendarProvider):
    name = "google-calendar-mcp"

    def __init__(
        self,
        transport: CalendarTransport | None,
        create_tool: str = "google_calendar.create_event",
        update_tool: str = "google_calendar.update_event",
        delete_tool: str = "google_calendar.delete_event",
        list_tools_method: str = "tools/list",
        list_templates_method: str = "prompts/list",
        list_resources_method: str = "resources/list",
        default_calendar_id: str = "",
    ) -> None:
        self.transport = transport
        self.create_tool = create_tool
        self.update_tool = update_tool
        self.delete_tool = delete_tool
        self.list_tools_method = list_tools_method
        self.list_templates_method = list_templates_method
        self.list_resources_method = list_resources_method
        self.default_calendar_id = default_calendar_id

    def is_available(self) -> bool:
        return self.transport.is_available() if self.transport is not None else False

    def describe_capabilities(self) -> CalendarCapabilitySnapshot:
        if self.transport is None or not self.transport.is_available():
            return CalendarCapabilitySnapshot()

        tools = self._extract_names(self.transport.list_tools())
        templates = self._extract_names(self.transport.list_templates())
        data_sources = self._extract_names(self.transport.list_resources())
        return CalendarCapabilitySnapshot(tools=tools, templates=templates, data_sources=data_sources)

    def create_event(self, event: Event, user: User) -> CalendarSyncResult:
        return self._call_tool("create", self.create_tool, event, user)

    def update_event(self, event: Event, user: User) -> CalendarSyncResult:
        return self._call_tool("update", self.update_tool, event, user)

    def delete_event(self, event: Event, user: User) -> CalendarSyncResult:
        return self._call_tool("delete", self.delete_tool, event, user)

    def _call_tool(self, action: str, tool_name: str, event: Event, user: User) -> CalendarSyncResult:
        if self.transport is None or not self.transport.is_available():
            return self._fallback_result(action, event, user, "MCP no disponible")

        if action in {"update", "delete"} and not self._resolve_external_event_id(event):
            return self._fallback_result(
                action,
                event,
                user,
                "event_id de Google no disponible; crea el evento primero para enlazarlo",
            )

        payload = self._build_payload(action, event, user)
        try:
            response = self.transport.call_tool(tool_name, payload)
        except Exception as error:
            logger.warning("MCP calendar sync failed for %s: %s", action, error)
            return self._fallback_result(action, event, user, str(error))

        message = self._extract_message(response) or f"Evento sincronizado con {self.name}"
        external_id = self._extract_external_id(response)
        capabilities = self.describe_capabilities()
        return CalendarSyncResult(
            success=True,
            provider_name=self.name,
            action=action,
            message=message,
            external_id=external_id,
            fallback_used=False,
            payload=payload,
            capabilities=capabilities,
        )

    def _fallback_result(self, action: str, event: Event, user: User, reason: str) -> CalendarSyncResult:
        payload = self._build_payload(action, event, user)
        return CalendarSyncResult(
            success=False,
            provider_name=self.name,
            action=action,
            message=f"Sincronización MCP no disponible: {reason}",
            fallback_used=True,
            payload=payload,
            capabilities=CalendarCapabilitySnapshot(),
        )

    def _build_payload(self, action: str, event: Event, user: User) -> dict[str, Any]:
        calendar_id = (self.default_calendar_id or "primary").strip()
        source_dt = event.start_time if event.start_time.tzinfo is not None else event.start_time.replace(tzinfo=UTC)
        end_dt = event.end_time if event.end_time.tzinfo is not None else event.end_time.replace(tzinfo=UTC)
        payload: dict[str, Any] = {
            "calendar_id": calendar_id or "primary",
            "title": event.title,
            "start_time_utc": source_dt.astimezone(UTC).isoformat(),
            "end_time_utc": end_dt.astimezone(UTC).isoformat(),
            "description": event.description,
            "location": event.location,
        }

        oauth_credentials = None
        if isinstance(user.preferences, dict):
            raw_credentials = user.preferences.get("google_calendar_oauth")
            if isinstance(raw_credentials, dict) and raw_credentials:
                oauth_credentials = raw_credentials
        if oauth_credentials is not None:
            payload["oauth_credentials"] = oauth_credentials

        if action in {"update", "delete"}:
            payload["event_id"] = self._resolve_external_event_id(event)

        if action == "delete":
            # API only requires identifiers for delete; avoid sending extra fields.
            return {
                "calendar_id": payload["calendar_id"],
                "event_id": payload["event_id"],
            }

        return payload

    def _resolve_external_event_id(self, event: Event) -> str | None:
        metadata = event.metadata if isinstance(event.metadata, dict) else {}
        for key in ("google_calendar_event_id", "external_id", "event_id", "calendar_event_id"):
            raw_value = metadata.get(key)
            if isinstance(raw_value, str) and raw_value.strip():
                return raw_value.strip()
            if isinstance(raw_value, int):
                return str(raw_value)
        return None

    def _extract_names(self, response: dict[str, Any]) -> list[str]:
        raw_items = response.get("tools") or response.get("prompts") or response.get("resources") or []
        if not isinstance(raw_items, list):
            return []

        names: list[str] = []
        for item in raw_items:
            if isinstance(item, dict):
                name = item.get("name") or item.get("uri")
                if isinstance(name, str) and name.strip():
                    names.append(name.strip())
        return names

    def _extract_message(self, response: dict[str, Any]) -> str | None:
        content = response.get("content")
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict):
                text = first.get("text")
                if isinstance(text, str) and text.strip():
                    return text.strip()

        text = response.get("message")
        if isinstance(text, str) and text.strip():
            return text.strip()

        result_text = response.get("result_text")
        if isinstance(result_text, str) and result_text.strip():
            return result_text.strip()

        return None

    def _extract_external_id(self, response: dict[str, Any]) -> str | None:
        for key in ("external_id", "id", "event_id", "calendar_event_id"):
            value = response.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, int):
                return str(value)
        return None