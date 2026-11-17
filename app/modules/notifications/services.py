"""Notifikasi di dalam aplikasi (ikon lonceng). Dihitung dari data pengajuan saat diminta; tidak disimpan
dan tidak ada status "sudah dibaca" (SD 5.1). Bukan email/WhatsApp/SMS.

- Supervisor: pengajuan berstatus Menunggu, usulan koreksi tanggal kedaluwarsa yang menunggu, dan penyesuaian
  stok 7 hari terakhir yang belum dicek ulang (hilang setelah Supervisor mengecek fisik kiriman itu).
  Stok menipis TIDAK masuk lonceng; itu ada di kartu dashboard dan laporan Stok menipis.
- Staff: pengajuan Disetujui yang belum diselesaikan (milik siapa pun, karena Staff mana pun boleh
  menyelesaikan), pengajuan miliknya yang Ditolak dalam 7 hari terakhir, dan ringkasan batch yang sudah
  waktunya dicek fisik.
- Admin: penyesuaian stok 7 hari terakhir yang belum dicek ulang (pengawasan; Admin tidak menjalankan operasional).
"""
from datetime import datetime, timezone

from ...common.constants import ROLE_ADMIN, ROLE_STAFF, ROLE_SUPERVISOR
from ..dashboard.services import unreviewed_adjustments
from ..movements import services as movements
from ..requests import services as requests

MAX_ITEMS = 30


def _label(item):
    return f"{item['request_number']} · {requests.TYPE_LABELS[item['request_type']]} {item['quantity']} " \
           f"{item.get('unit') or ''} {item.get('product_name') or '-'} (kiriman {item.get('batch_number') or '-'})"


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des")


def _date(iso):
    """'2026-12-14' -> '14 Des 2026' (sama dengan format tanggal di layar)."""
    try:
        year, month, day = (int(x) for x in str(iso)[:10].split("-"))
        return f"{day} {_MONTHS[month - 1]} {year}"
    except (ValueError, IndexError):
        return str(iso)


def _waiting(at):
    days = requests.waiting_days(at)
    return "hari ini" if days == 0 else f"{days} hari"


def build(db, user):
    items = []
    if user["role"] == ROLE_SUPERVISOR:
        pending = requests.enrich(db, list(db.handling_requests.find({"status": "pending"})
                                           .sort("submitted_at", 1).limit(MAX_ITEMS)))
        for r in pending:
            items.append({"kind": "review_needed", "request_id": str(r["_id"]), "at": r["submitted_at"],
                          "title": "Menunggu persetujuan Anda",
                          "text": f"{_label(r)} diajukan {r['submitted_by_name']} · menunggu {_waiting(r['submitted_at'])}"})

    if user["role"] == ROLE_SUPERVISOR:
        corrections = list(db.inspections.find({"expiry_correction.status": "pending"}).sort("inspected_at", 1)
                           .limit(MAX_ITEMS))
        batches = {b["_id"]: b for b in db.batches.find({"_id": {"$in": [c["batch_id"] for c in corrections]}},
                                                        {"batch_number": 1})}
        names = {u["_id"]: u["name"] for u in db.master_karyawan.find(
            {"_id": {"$in": [c.get("inspected_by") for c in corrections]}}, {"name": 1})}
        for c in corrections:
            fix = c["expiry_correction"]
            items.append({"kind": "expiry_correction", "inspection_id": str(c["_id"]), "at": c["inspected_at"],
                          "title": "Usulan koreksi tanggal kedaluwarsa",
                          "text": f"Kiriman {batches.get(c['batch_id'], {}).get('batch_number', '-')}: tercatat "
                                  f"{_date(fix['old_date'])}, di kemasan {_date(fix['proposed_date'])} · dari "
                                  f"{names.get(c.get('inspected_by'), '-')}"})

    if user["role"] in (ROLE_SUPERVISOR, ROLE_ADMIN):
        # Hilang sendiri setelah Supervisor mencatat cek fisik pada kiriman yang sama (lihat unreviewed_adjustments).
        adjusted = movements.enrich(db, unreviewed_adjustments(db)[:MAX_ITEMS])
        for m in adjusted:
            sign = "+" if m["movement_type"] == "adjustment_in" else "-"
            items.append({"kind": "adjustment", "batch_id": str(m["batch_id"]), "at": m["created_at"],
                          "title": "Stok disamakan, belum dicek ulang",
                          "text": f"{m['product_name']} kiriman {m['batch_number']}: {sign}{m['quantity']} {m['unit'] or ''}"
                                  f" oleh {m['created_by_name']} · {m.get('notes') or m.get('reason') or ''}"})

    if user["role"] == ROLE_STAFF:
        from ..expiry.alerts import due_for_check
        due = due_for_check(db)
        if due:
            critical = sum(1 for b in due if b["expiry_status"] == "critical")
            extra = f", {critical} di antaranya Kritis" if critical else ""
            items.append({"kind": "check_due", "at": datetime.now(timezone.utc),
                          "title": f"{len(due)} kiriman perlu dicek fisik",
                          "text": f"Sudah waktunya dicek menurut jadwal{extra}. Buka Pantau Kedaluwarsa > Perlu dicek."})
        approved = requests.enrich(db, list(db.handling_requests.find({"status": "approved"})
                                            .sort("reviewed_at", 1).limit(MAX_ITEMS)))
        for r in approved:
            items.append({"kind": "approved", "request_id": str(r["_id"]), "at": r["reviewed_at"],
                          "title": "Disetujui, belum diselesaikan",
                          "text": f"{_label(r)} disetujui {r['reviewed_by_name']} · menunggu {_waiting(r['reviewed_at'])}"})
        rejected = requests.enrich(db, list(db.handling_requests.find(
            {"status": "rejected", "submitted_by": user["_id"], "reviewed_at": {"$gte": requests.rejected_since()}})
            .sort("reviewed_at", -1).limit(MAX_ITEMS)))
        for r in rejected:
            items.append({"kind": "rejected", "request_id": str(r["_id"]), "at": r["reviewed_at"],
                          "title": "Pengajuan Anda ditolak",
                          "text": f"{_label(r)} ditolak {r['reviewed_by_name']}: {r['review_note']}"})

    items.sort(key=lambda i: i["at"].replace(tzinfo=None) if i["at"] else datetime.min, reverse=True)
    return {"count": len(items), "items": items[:MAX_ITEMS]}
