"""Penjaga kesalahan tampilan yang tidak terlihat oleh tes server."""
import os
import re

JS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public", "static", "js")


def test_filter_all_options_never_use_an_empty_id():
    """Webix mengganti id kosong dengan nomor acak. Bila pilihan "Semua ..." dipilih, nomor itu terkirim ke server
    sebagai filter dan ditolak ("... tidak valid"). Pilihan "Semua" harus memakai SE.ALL."""
    offenders = []
    for name in sorted(os.listdir(JS_DIR)):
        if not name.endswith(".js"):
            continue
        with open(os.path.join(JS_DIR, name), encoding="utf-8") as handle:
            for number, line in enumerate(handle, 1):
                if re.search(r'\{\s*id:\s*""\s*,\s*value:', line):
                    offenders.append(f"{name}:{number}")
    assert not offenders, "Pilihan dengan id kosong (pakai SE.ALL): " + ", ".join(offenders)


def test_query_builder_ignores_the_all_marker():
    with open(os.path.join(JS_DIR, "common.js"), encoding="utf-8") as handle:
        source = handle.read()
    assert 'SE.ALL = "__all__"' in source
    assert "params[k] !== SE.ALL" in source
