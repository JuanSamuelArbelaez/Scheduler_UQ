from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
import re
import unicodedata
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from models.entities import Event


@dataclass(slots=True)
class ParsedCreateRequest:
    title: str
    start_time: datetime
    end_time: datetime
    description: str | None


@dataclass(slots=True)
class ParsedUpdateRequest:
    event_id: int | None
    title_query: str | None
    new_start: datetime


@dataclass(slots=True)
class ParsedCancelRequest:
    event_id: int | None
    title_query: str | None


def _extract_timezone(text: str, default_timezone: str) -> str | None:
    normalized = text.strip()
    if not normalized:
        return None

    utc_match = re.search(r"\butc\s*([+-])\s*(\d{1,2})\b", normalized, flags=re.IGNORECASE)
    if utc_match:
        sign = -1 if utc_match.group(1) == "-" else 1
        hours = int(utc_match.group(2))
        offset = sign * hours
        mapping = {
            -5: "America/Bogota",
            -6: "America/Guatemala",
            -4: "America/La_Paz",
            0: "UTC",
            1: "Europe/Madrid",
        }
        return mapping.get(offset, default_timezone)

    lowered = _normalize_text(normalized)
    if "colombia" in lowered or "bogota" in lowered:
        return "America/Bogota"

    match = re.search(r"\b([A-Za-z_]+/[A-Za-z_]+)\b", normalized)
    if match:
        return match.group(1)
    return None


def _to_utc_datetime(value: datetime, timezone_name: str) -> datetime:
    user_zone = _resolve_timezone(timezone_name)
    localized = value.replace(tzinfo=user_zone) if value.tzinfo is None else value.astimezone(user_zone)
    return localized.astimezone(UTC)


def _to_user_timezone(value: datetime, timezone_name: str) -> datetime:
    user_zone = _resolve_timezone(timezone_name)
    source = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return source.astimezone(user_zone)


def _now_in_timezone(timezone_name: str) -> datetime:
    return datetime.now(_resolve_timezone(timezone_name))


def _resolve_timezone(timezone_name: str) -> timezone | ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        lowered = _normalize_text(timezone_name)
        if lowered in {"america/bogota", "bogota", "colombia", "utc-5"}:
            return timezone(timedelta(hours=-5))
        if lowered in {"utc", "etc/utc", "utc+0", "gmt"}:
            return timezone.utc
        utc_match = re.match(r"^utc([+-])(\d{1,2})$", lowered)
        if utc_match:
            sign = -1 if utc_match.group(1) == "-" else 1
            hours = int(utc_match.group(2))
            return timezone(timedelta(hours=sign * hours))
        return timezone(timedelta(hours=-5))


def _resolve_date(values: dict[str, str | None], reference_now: datetime | None = None) -> date:
    today = (reference_now or datetime.now()).date()

    if values.get("date"):
        return date.fromisoformat(values["date"] or "")

    if values.get("day_num") and values.get("month_name") and values.get("year"):
        month_map = {
            "enero": 1,
            "febrero": 2,
            "marzo": 3,
            "abril": 4,
            "mayo": 5,
            "junio": 6,
            "julio": 7,
            "agosto": 8,
            "septiembre": 9,
            "setiembre": 9,
            "octubre": 10,
            "noviembre": 11,
            "diciembre": 12,
        }
        month_value = month_map.get(_normalize_text(values["month_name"] or ""))
        if month_value is None:
            raise ValueError("Mes inválido")
        return date(year=int(values["year"] or "0"), month=month_value, day=int(values["day_num"] or "0"))

    day_name = _normalize_text(values.get("day") or "")
    if day_name == "hoy":
        return today
    if day_name in {"manana", "mañana"}:
        return today + timedelta(days=1)
    if day_name == "pasado":
        return today - timedelta(days=1)
    if day_name == "anteayer":
        return today - timedelta(days=2)

    weekday_map = {
        "lunes": 0,
        "martes": 1,
        "miercoles": 2,
        "miércoles": 2,
        "jueves": 3,
        "viernes": 4,
        "sabado": 5,
        "sábado": 5,
        "domingo": 6,
    }
    if day_name in weekday_map:
        target_weekday = weekday_map[day_name]
        current_weekday = today.weekday()
        delta = (target_weekday - current_weekday) % 7
        if delta == 0:
            return today + timedelta(days=7)
        return today + timedelta(days=delta)

    return today


def _resolve_time(hour_raw: str | None, minute_raw: str | None, ampm_raw: str | None) -> time:
    hour = int(hour_raw or "0")
    minute = int(minute_raw or "0")
    ampm = _normalize_text(ampm_raw or "")

    if ampm in {"de la manana", "de la mañana"}:
        pass
    elif ampm in {"de la tarde", "de la noche"} and hour < 12:
        hour += 12
    elif ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0

    if not (0 <= hour <= 23):
        raise ValueError(f"Hora inválida: {hour}")
    if not (0 <= minute <= 59):
        raise ValueError(f"Minutos inválidos: {minute}")

    return time(hour=hour, minute=minute)


def _clean_create_title(text: str) -> str:
    cleaned = text
    cleaned = re.sub(r"^(una\s+)?cita\s+para\s+", "", cleaned).strip()
    cleaned = re.sub(r"^(un\s+)?evento\s+para\s+", "", cleaned).strip()
    cleaned = re.sub(r"^para\s+", "", cleaned).strip()
    cleaned = re.sub(r"\b(voy\s+a\s+ir|ire|ir)\b", "", cleaned).strip(" .,")
    return " ".join(cleaned.split())


def _clean_title_query(text: str) -> str:
    normalized = _normalize_text(text)
    cleaned = re.sub(r"\b(la|el|mi|cita|evento|de|del)\b", " ", normalized)
    return " ".join(cleaned.split())


def _parse_natural_create(text: str, reference_now: datetime | None = None) -> ParsedCreateRequest | None:
    normalized = _normalize_text(text)
    patterns = [
        r"(?:agenda|agendar|programa|crear|crea|agrega|anade|añade|haz)\s+(?P<title>.+?)\s+(?:el\s+)?(?P<day>hoy|manana|mañana|lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingo|pasado)\s+(?:a\s+las?\s+|a\s+)(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm|de la manana|de la mañana|de la tarde|de la noche)?",
        r"(?:agenda|agendar|programa|crear|crea|agrega|anade|añade|haz)\s+(?P<title>.+?)\s+(?:el\s+)?(?P<date>\d{4}-\d{2}-\d{2})\s+(?:a\s+las?\s+|a\s+)(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm|de la manana|de la mañana|de la tarde|de la noche)?",
        r"(?:agenda|agendar|programa|crear|crea|agrega|anade|añade|haz)\s+(?P<title>.+?)\s+(?:el\s+)?(?:(?:lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingo)\s+)?(?P<day_num>\d{1,2})\s+de\s+(?P<month_name>enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+(?:de\s+)?(?P<year>\d{4})(?P<between>.*?)\s*(?:a\s+las?\s+|a\s+)?(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm|de la manana|de la mañana|de la tarde|de la noche)?",
        r"(?:agenda|agendar|programa|crear|crea|agrega|anade|añade|haz)\s+(?P<title>.+?)\s+(?:el\s+)?(?P<day>hoy|manana|mañana|lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingo|pasado)\s+(?:a\s+|al\s+)(?P<time>mediodia|mediodía|medianoche)",
        r"(?:agenda|agendar|programa|crear|crea|agrega|anade|añade|haz)\s+(?P<title>.+?)\s+(?:el\s+)?(?P<day>hoy|manana|mañana)\s+(?:a\s+las?\s+|a\s+)(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm|de la manana|de la mañana|de la tarde|de la noche)?",
    ]

    for pattern in patterns:
        day_match = re.search(pattern, normalized, re.IGNORECASE)
        if day_match:
            break
    else:
        return None

    title = day_match.group("title").strip(" .,")
    between = (day_match.groupdict().get("between") or "").strip(" .,")
    if between:
        title = f"{title} {between}".strip()
    title = _clean_create_title(title)
    if not title:
        return None

    try:
        if "time" in day_match.groupdict() and day_match.group("time"):
            time_expr = day_match.group("time").lower()
            if time_expr in {"mediodia", "mediodía"}:
                event_time = time(12, 0)
            elif time_expr == "medianoche":
                event_time = time(0, 0)
            else:
                event_time = time(9, 0)
        else:
            event_time = _resolve_time(day_match.group("hour"), day_match.group("minute"), day_match.group("ampm"))
        event_date = _resolve_date(day_match.groupdict(), reference_now=reference_now)
    except ValueError:
        return None

    start_time = datetime.combine(event_date, event_time)
    duration = timedelta(hours=1)
    if "cita" in title.lower() or "consulta" in title.lower():
        duration = timedelta(minutes=30)

    return ParsedCreateRequest(title=title, start_time=start_time, end_time=start_time + duration, description=None)


def _parse_natural_cancel_request(text: str) -> ParsedCancelRequest | None:
    normalized = _normalize_text(text)
    id_match = re.search(r"\b(\d+)\b", normalized)
    if id_match is not None:
        return ParsedCancelRequest(event_id=int(id_match.group(1)), title_query=None)

    title_match = re.search(r"(?:cancela|cancelar|elimina|borra|anula)\s+(?P<title>.+)$", normalized)
    if title_match is None:
        return None

    title_query = _clean_title_query(title_match.group("title"))
    if not title_query:
        return None
    return ParsedCancelRequest(event_id=None, title_query=title_query)


def _parse_natural_update(text: str, reference_now: datetime | None = None) -> ParsedUpdateRequest | None:
    normalized = _normalize_text(text)
    timing_matches = list(
        re.finditer(
            r"(?:a|para)\s+(?:(?P<day>hoy|manana|mañana|lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingo)\s+)?(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)?",
            normalized,
        )
    )
    if not timing_matches:
        return None

    timing_match = timing_matches[-1]
    try:
        event_date = _resolve_date(timing_match.groupdict(), reference_now=reference_now)
        event_time = _resolve_time(timing_match.group("hour"), timing_match.group("minute"), timing_match.group("ampm"))
    except ValueError:
        return None

    before_timing = normalized[: timing_match.start()].strip()
    id_match = re.search(r"\b(\d+)\b", before_timing)
    if id_match is not None:
        return ParsedUpdateRequest(event_id=int(id_match.group(1)), title_query=None, new_start=datetime.combine(event_date, event_time))

    title_match = re.search(r"(?:mueve|cambia|modifica|reprograma|actualiza)\s+(?P<title>.+)$", before_timing)
    if title_match is None:
        return None

    title_query = _clean_title_query(title_match.group("title"))
    if not title_query:
        return None
    return ParsedUpdateRequest(event_id=None, title_query=title_query, new_start=datetime.combine(event_date, event_time))


def _resolve_event_selection(request: ParsedCancelRequest | None, events: list[Event]) -> Event | list[Event] | None:
    if request is None:
        return None

    if request.event_id is not None:
        for event in events:
            if event.id == request.event_id and event.status != "cancelled":
                return event
        return None

    if not request.title_query:
        return None

    candidates = _find_event_candidates(request.title_query, events)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    return candidates[:5]


def _find_event_candidates(query: str, events: list[Event]) -> list[Event]:
    query_tokens = [token for token in re.split(r"\W+", _normalize_text(query)) if token]
    if not query_tokens:
        return []

    scored: list[tuple[int, Event]] = []
    for event in events:
        if event.status == "cancelled":
            continue
        title_tokens = set(re.split(r"\W+", _normalize_text(event.title)))
        score = sum(1 for token in query_tokens if token in title_tokens)
        if score > 0:
            scored.append((score, event))

    scored.sort(key=lambda item: (-item[0], item[1].start_time))
    return [event for _, event in scored]


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    without_marks = "".join(character for character in normalized if not unicodedata.combining(character))
    return " ".join(without_marks.split())