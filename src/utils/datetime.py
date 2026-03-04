import re
from datetime import datetime, timezone


class DatetimeUtils:
    """Date/time parsing helpers for Steam achievement pages."""

    # Matches patterns like "Unlocked 15 Jan, 2024 @ 3:42pm"
    _UNLOCK_RE = re.compile(
        r'(\d{1,2})\s+(\w+),?\s+(\d{4})\s*@\s*(\d{1,2}):(\d{2})(am|pm)',
        re.IGNORECASE,
    )

    _MONTHS = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
        'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
        'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    }

    _NOON = 12

    @classmethod
    def parse_unlock_time(cls, raw: str) -> datetime | None:
        """Parse a Steam unlock timestamp string into a UTC datetime.

        Expected input examples:
            "Unlocked 15 Jan, 2024 @ 3:42pm"
            "Unlocked 1 Dec, 2023 @ 12:00am"

        Returns None when the string cannot be parsed.
        """
        match = cls._UNLOCK_RE.search(raw)
        if not match:
            return None

        day = int(match.group(1))
        month_str = match.group(2).lower()[:3]
        year = int(match.group(3))
        hour = int(match.group(4))
        minute = int(match.group(5))
        ampm = match.group(6).lower()

        month = cls._MONTHS.get(month_str)
        if month is None:
            return None

        if ampm == 'pm' and hour != cls._NOON:
            hour += cls._NOON
        elif ampm == 'am' and hour == cls._NOON:
            hour = 0

        try:
            return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
        except ValueError:
            return None
