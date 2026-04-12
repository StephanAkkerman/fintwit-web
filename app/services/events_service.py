from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from lxml.html import fromstring

logger = logging.getLogger(__name__)

_INVESTING_EVENTS_URL = (
    "https://www.investing.com/economic-calendar/Service/getCalendarFilteredData"
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
}

_FORM_DATA: dict[str, object] = {
    "country[]": [72, 5],  # United States and Euro zone
    "importance[]": 3,  # three-star events
    "timeZone": 8,
    "timeFilter": "timeRemain",
    "currentTab": "thisWeek",
    "submitFilters": 1,
    "limit_from": 0,
}

_IMPACT_EMOJI = {
    1: "🟨",
    2: "🟧",
    3: "🟥",
}


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    return normalized or None


def _parse_day_id(day_id: str | None) -> str | None:
    if not day_id or not day_id.startswith("theDay"):
        return None

    raw = day_id.replace("theDay", "", 1)
    if not raw.isdigit():
        return None

    try:
        dt = datetime.fromtimestamp(int(raw), tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None

    return dt.strftime("%d/%m/%Y")


def _parse_impact_score(cell) -> int | None:
    classes = (cell.get("class") or "").lower()
    if "sentiment" not in classes:
        return None

    icon_count = len(
        cell.xpath(
            ".//*[contains(@class, 'bullishIcon') or contains(@class, 'BullishIcon')]"
        )
    )
    if icon_count > 0:
        return max(1, min(icon_count, 3))

    text_value = (cell.text_content() or "").lower()
    if "high" in text_value:
        return 3
    if "medium" in text_value:
        return 2
    if "low" in text_value:
        return 1

    return None


def _parse_events_table(html_fragment: str, limit: int) -> list[dict]:
    root = fromstring(html_fragment)
    rows = root.xpath(".//tr")

    current_date: str | None = None
    events: list[dict] = []

    for row in rows:
        row_id = row.get("id")

        # Date-separator row; contains id like theDay1712793600
        if row_id is None:
            cells = row.xpath("./td")
            if cells:
                current_date = _parse_day_id(cells[0].get("id")) or current_date
            continue

        if not row_id.startswith("eventRowId_"):
            continue

        event_id = row_id.replace("eventRowId_", "", 1)
        time_value = zone_value = currency_value = event_value = None
        actual_value = forecast_value = previous_value = None
        impact_score = None

        for cell in row.xpath("./td"):
            classes = cell.get("class") or ""
            cell_id = cell.get("id") or ""

            if "first left" in classes:
                time_value = _clean_text(cell.text_content())
                continue

            if "flagCur" in classes:
                spans = cell.xpath(".//span")
                if spans:
                    zone_value = _clean_text((spans[0].get("title") or "").lower())
                currency_value = _clean_text(cell.text_content())
                continue

            if "left event" in classes:
                event_value = _clean_text(cell.text_content())
                continue

            parsed_impact = _parse_impact_score(cell)
            if parsed_impact is not None:
                impact_score = parsed_impact
                continue

            if cell_id == f"eventActual_{event_id}":
                actual_value = _clean_text(cell.text_content())
                continue

            if cell_id == f"eventForecast_{event_id}":
                forecast_value = _clean_text(cell.text_content())
                continue

            if cell_id == f"eventPrevious_{event_id}":
                previous_value = _clean_text(cell.text_content())

        if event_value is None:
            continue

        normalized_impact = impact_score or int(_FORM_DATA.get("importance[]", 3))
        normalized_impact = max(1, min(normalized_impact, 3))

        events.append(
            {
                "id": event_id,
                "date": current_date,
                "time": time_value,
                "zone": zone_value,
                "currency": currency_value,
                "event": event_value,
                "actual": actual_value,
                "forecast": forecast_value,
                "previous": previous_value,
                "impact_score": normalized_impact,
                "impact_emoji": _IMPACT_EMOJI.get(normalized_impact),
                "source": "https://www.investing.com/economic-calendar/",
            }
        )

        if len(events) >= limit:
            break

    return events


async def get_economic_events(
    client: httpx.AsyncClient, limit: int = 25
) -> list[dict] | None:
    """Fetch high-impact US and EU economic events for the current week."""
    bounded_limit = max(1, min(int(limit), 100))

    try:
        response = await client.post(
            _INVESTING_EVENTS_URL,
            headers=_HEADERS,
            data=_FORM_DATA,
        )
        if response.status_code != 200:
            logger.warning(
                "Could not fetch Investing economic events: status=%s",
                response.status_code,
            )
            return None

        payload = response.json()
    except (httpx.RequestError, ValueError) as exc:
        logger.warning("Could not fetch Investing economic events: %s", exc)
        return None

    html_fragment = payload.get("data")
    if not isinstance(html_fragment, str):
        return []

    try:
        return _parse_events_table(html_fragment, limit=bounded_limit)
    except Exception as exc:
        logger.warning("Could not parse Investing economic events: %s", exc)
        return []
