"""Error khusus aplikasi. Pesannya aman ditampilkan ke pengguna (tanpa detail internal)."""


class AppError(Exception):
    status = 400

    def __init__(self, message, fields=None, status=None):
        super().__init__(message)
        self.message = message
        self.fields = fields or {}
        if status is not None:
            self.status = status


class ValidationFailed(AppError):
    status = 400


class Unauthorized(AppError):
    status = 401


class Forbidden(AppError):
    status = 403


class NotFound(AppError):
    status = 404


class Conflict(AppError):
    status = 409
