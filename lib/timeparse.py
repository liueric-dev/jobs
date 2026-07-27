"""Timestamp normalisation -- one canonical instant from many source shapes.

THE BUG THIS EXISTS TO FIX
    `public.events.start_datetime` was TEXT holding two mutually incompatible
    formats written by different scripts:

        nyc_permitted_events / nyc_parks_events   2026-07-24T19:00:00.000
        nypl_events / qpl_events                  2026-07-24T19:00:00+00:00

    The first form is Socrata's, and it is naive *America/New_York local
    time*. The second is a real UTC instant. Stored in one TEXT column they
    string-compare as though they were on the same clock, so every
    cross-source ordering, window filter and "what's on tonight" query was
    wrong by 4-5 hours for one of the two groups.

    A second, quieter bug came from the same column: lexicographic
    comparison of mixed-precision strings. Ticketmaster falls back to a
    date-only `localDate`, and

        '2026-07-25' < '2026-07-25T00:00:00.000'   -> True

    because the shorter string is a prefix. Every prune therefore deleted
    date-only events on the morning of the day they happened.

    Both classes of bug disappear once the comparison happens on a real
    TIMESTAMPTZ instead of on text. Callers store the parsed instant in
    start_ts/end_ts and keep the original string untouched for debugging.

DST
    Naive local values are attached to America/New_York with .replace(), and
    zoneinfo resolves the correct offset for that date -- so EDT/EST is
    handled per-timestamp rather than with a fixed -4/-5. During the autumn
    fall-back hour a naive local time is genuinely ambiguous; Python's
    default fold=0 picks the first (daylight) occurrence. One hour a year,
    on events that are rarely scheduled at 01:30, is an acceptable trade
    against the alternative of rejecting the value outright.
"""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

NYC = ZoneInfo("America/New_York")
UTC = timezone.utc

#: Epoch seconds below this are treated as a bad value rather than 1970.
#: Both pipelines only ever handle contemporary events; a 0/garbage epoch is
#: far more likely to be a missing field than a real 1970s timestamp.
_MIN_PLAUSIBLE_EPOCH = 946_684_800  # 2000-01-01T00:00:00Z


def to_utc(value, assume_tz=NYC):
    """Coerce a timestamp of unknown shape to an aware UTC datetime.

    Accepts: None/"" (-> None), datetime, date, epoch seconds (int/float or
    an all-digit string), or an ISO-8601 string with or without an offset.

    A value that already carries an offset is trusted and merely converted.
    A naive value is interpreted in `assume_tz` -- which is the whole point:
    Socrata's naive strings are NYC local, and treating them as UTC is the
    original bug.

    Returns None for anything unparseable, so a single malformed row can't
    abort a batch. Callers that care can check for None.
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        return (value.replace(tzinfo=assume_tz) if value.tzinfo is None
                else value).astimezone(UTC)

    if isinstance(value, date):
        # Date-only: midnight *local*, not midnight UTC.
        return datetime(value.year, value.month, value.day,
                        tzinfo=assume_tz).astimezone(UTC)

    if isinstance(value, (int, float)):
        return _from_epoch(value)

    text = str(value).strip()
    if not text:
        return None

    # Socrata occasionally emits bare epoch seconds in otherwise-ISO columns.
    if text.isdigit():
        return _from_epoch(int(text))

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    return (parsed.replace(tzinfo=assume_tz) if parsed.tzinfo is None
            else parsed).astimezone(UTC)


def _from_epoch(seconds):
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        return None
    if seconds < _MIN_PLAUSIBLE_EPOCH:
        return None
    return datetime.fromtimestamp(seconds, tz=UTC)


def utc_now():
    """Aware current UTC time."""
    return datetime.now(UTC)


def utc_now_str():
    """Bookkeeping timestamp: 'YYYY-MM-DDTHH:MM:SS', UTC, no offset suffix.

    This exact format is load-bearing and must not gain an offset or
    microseconds. Both pipelines compare these as *strings* (WHERE last_seen
    < %s, watermark > cutoff), and jobs/ additionally relies on "" sorting
    before every real timestamp as its "never run" sentinel. Widening the
    format would silently break both.
    """
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")


def day_bounds_utc(days_ahead, tz=NYC):
    """(start, end) UTC instants for "local midnight today" .. "+days_ahead".

    Ingest windows are conceptually local -- "events over the next 90 days"
    means NYC days -- so the boundary is computed locally then converted,
    rather than slicing UTC and drifting by the offset.
    """
    from datetime import timedelta

    local_midnight = datetime.now(tz).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return (local_midnight.astimezone(UTC),
            (local_midnight + timedelta(days=days_ahead)).astimezone(UTC))
