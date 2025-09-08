# utils.py
from datetime import date, timedelta, datetime

def week_range_for_date(d: date):
    start = d - timedelta(days=d.weekday())  # Monday
    end = start + timedelta(days=6)
    return start, end

def datetime_start_of(d: date):
    return datetime.combine(d, datetime.min.time())

def datetime_end_of(d: date):
    return datetime.combine(d, datetime.max.time())
