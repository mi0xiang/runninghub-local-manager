"""Creation-time display metadata; never use activity timestamps or mutate records."""
import datetime
import os


def timestamp(value):
    if not isinstance(value, str) or not value:
        return 0.0
    try:
        parsed = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.timestamp() if parsed.tzinfo is not None else 0.0
    except (ValueError, OverflowError, OSError):
        return 0.0


def created_at(root, entry):
    for name in ('created_at', 'createdAt'):
        value = entry.get(name)
        if timestamp(value):
            return value
    folder = (root / entry['path']).resolve()
    base = (root / 'projects').resolve()
    if not folder.is_relative_to(base) or folder == base:
        return None
    try:
        info = folder.stat()
        birth = getattr(info, 'st_birthtime', None)
        if birth is None and os.name == 'nt':
            birth = info.st_ctime  # Windows creation time, never Unix metadata ctime.
        if birth is not None:
            return datetime.datetime.fromtimestamp(birth, datetime.timezone.utc).isoformat()
    except (OSError, ValueError, OverflowError):
        pass
    return None


def sort_key(item):
    return (timestamp(item.get('created_at') or item.get('createdAt')),
            str(item.get('project_id') or item.get('id') or ''))
