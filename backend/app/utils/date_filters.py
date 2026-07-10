from datetime import date, datetime

from sqlalchemy import func


def is_date_only(value: str) -> bool:
    value = value.strip()
    return len(value) == 10 and value[4] == "-" and value[7] == "-"


def parse_date_only(value: str) -> date:
    return datetime.strptime(value.strip(), "%Y-%m-%d").date()


def apply_created_at_start(query, column, start_date: str | None):
    if not start_date:
        return query
    if is_date_only(start_date):
        return query.filter(func.date(column) >= parse_date_only(start_date))
    try:
        start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        return query.filter(column >= start.replace(tzinfo=None))
    except ValueError:
        return query


def apply_created_at_end(query, column, end_date: str | None):
    if not end_date:
        return query
    if is_date_only(end_date):
        return query.filter(func.date(column) <= parse_date_only(end_date))
    try:
        end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        return query.filter(column <= end.replace(tzinfo=None))
    except ValueError:
        return query
