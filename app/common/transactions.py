"""Transaksi MongoDB: beberapa perubahan data berhasil bersama-sama atau dibatalkan semuanya.

Di MongoDB Atlas dipakai transaksi sungguhan. Database tiruan untuk pengujian tidak mendukungnya,
sehingga di sana perubahan dijalankan biasa (session = None).
"""
from contextlib import contextmanager


@contextmanager
def transaction(db):
    try:
        session = db.client.start_session()
    except (NotImplementedError, AttributeError):
        yield None
        return
    with session:
        with session.start_transaction():
            yield session
