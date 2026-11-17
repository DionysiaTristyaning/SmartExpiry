"""Audit log (riwayat aktivitas): hanya MENAMBAH catatan, tidak pernah mengubah atau menghapus."""
from datetime import datetime, timezone

from flask import has_request_context, request

_SECRET_WORDS = ("password", "token", "secret", "cookie", "hash")


def _safe_details(details):
    if not isinstance(details, dict):
        return {}
    return {
        key: value
        for key, value in details.items()
        if not any(word in key.lower() for word in _SECRET_WORDS)
    }


def log_action(db, actor, action, entity=None, entity_id=None, details=None, session=None):
    """Catat satu aktivitas. `actor` = dokumen pengguna (boleh None, misalnya login gagal)."""
    db.audit_logs.insert_one({
        "actor_id": actor["_id"] if actor else None,
        "actor_role": actor.get("role") if actor else None,
        "action": action,
        "entity": entity,
        "entity_id": entity_id,
        "details": _safe_details(details),
        "ip": request.remote_addr if has_request_context() else None,
        "created_at": datetime.now(timezone.utc),
    }, session=session)
