from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any

from models.entities import Event, User


@dataclass(slots=True)
class CalendarCapabilitySnapshot:
    tools: list[str] = field(default_factory=list)
    templates: list[str] = field(default_factory=list)
    data_sources: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CalendarSyncResult:
    success: bool
    provider_name: str
    action: str
    message: str
    external_id: str | None = None
    fallback_used: bool = False
    payload: dict[str, Any] = field(default_factory=dict)
    capabilities: CalendarCapabilitySnapshot = field(default_factory=CalendarCapabilitySnapshot)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CalendarTransport(ABC):
    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list_tools(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def list_templates(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def list_resources(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class CalendarProvider(ABC):
    name = "calendar"

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def describe_capabilities(self) -> CalendarCapabilitySnapshot:
        raise NotImplementedError

    @abstractmethod
    def create_event(self, event: Event, user: User) -> CalendarSyncResult:
        raise NotImplementedError

    @abstractmethod
    def update_event(self, event: Event, user: User) -> CalendarSyncResult:
        raise NotImplementedError

    @abstractmethod
    def delete_event(self, event: Event, user: User) -> CalendarSyncResult:
        raise NotImplementedError


class NoopCalendarProvider(CalendarProvider):
    name = "noop-calendar"

    def is_available(self) -> bool:
        return False

    def describe_capabilities(self) -> CalendarCapabilitySnapshot:
        return CalendarCapabilitySnapshot()

    def create_event(self, event: Event, user: User) -> CalendarSyncResult:
        return self._build_result("create", event, user, "Proveedor MCP no configurado")

    def update_event(self, event: Event, user: User) -> CalendarSyncResult:
        return self._build_result("update", event, user, "Proveedor MCP no configurado")

    def delete_event(self, event: Event, user: User) -> CalendarSyncResult:
        return self._build_result("delete", event, user, "Proveedor MCP no configurado")

    def _build_result(self, action: str, event: Event, user: User, message: str) -> CalendarSyncResult:
        payload = {
            "event_id": event.id,
            "user_id": user.id,
            "user_email": user.email,
            "timezone": str(user.preferences.get("timezone") or event.timezone),
        }
        return CalendarSyncResult(
            success=False,
            provider_name=self.name,
            action=action,
            message=message,
            fallback_used=True,
            payload=payload,
        )