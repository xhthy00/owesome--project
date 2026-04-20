"""Custom exceptions."""


class AppException(Exception):
    """Base application exception."""

    def __init__(self, message: str = "Internal server error", code: int = 500):
        self.message = message
        self.code = code
        super().__init__(self.message)


class NotFoundException(AppException):
    """Resource not found exception."""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(message=message, code=404)


class BadRequestException(AppException):
    """Bad request exception."""

    def __init__(self, message: str = "Bad request"):
        super().__init__(message=message, code=400)


class UnauthorizedException(AppException):
    """Unauthorized exception."""

    def __init__(self, message: str = "Unauthorized"):
        super().__init__(message=message, code=401)


class ForbiddenException(AppException):
    """Forbidden exception."""

    def __init__(self, message: str = "Forbidden"):
        super().__init__(message=message, code=403)


class ValidationException(AppException):
    """Validation exception."""

    def __init__(self, message: str = "Validation error", errors: list = None):
        super().__init__(message=message, code=422)
        self.errors = errors or []


class DatabaseException(AppException):
    """Database exception."""

    def __init__(self, message: str = "Database error"):
        super().__init__(message=message, code=500)


class DatasourceException(AppException):
    """Datasource connection exception."""

    def __init__(self, message: str = "Datasource connection failed"):
        super().__init__(message=message, code=400)