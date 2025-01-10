from collections.abc import Mapping
from typing import Union

from starlette.exceptions import HTTPException


class ASGIAdminError(Exception):
    """
    Base class for all exceptions raised by ASGI Admin.

    Parameters:
        message: The error message.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class ASGIAdminConfigurationError(ASGIAdminError):
    """
    Base class for all configuration exceptions raised by ASGI Admin.

    Parameters:
        message: The error message.
    """


class ASGIAdminHTTPException(HTTPException, ASGIAdminError):
    """
    Base class for all HTTP exceptions raised by ASGI Admin.

    Parameters:
        status_code: The status code of the HTTP response.
        detail: The error message.
        headers: Optional additional headers to include in the HTTP response.
    """

    def __init__(
        self,
        status_code: int,
        detail: str,
        headers: Union[Mapping[str, str], None] = None,
    ) -> None:
        super().__init__(status_code, detail, headers)
        super(ASGIAdminError, self).__init__(detail)


class ASGIAdminNotFound(ASGIAdminHTTPException):
    """
    Raised when a requested resource is not found.

    Parameters:
        detail: The error message.
        headers: Optional additional headers to include in the HTTP response.
    """

    def __init__(
        self,
        detail: str = "Not Found",
        headers: Union[Mapping[str, str], None] = None,
    ) -> None:
        super().__init__(404, detail, headers=headers)


__all__ = [
    "ASGIAdminError",
    "ASGIAdminConfigurationError",
    "ASGIAdminHTTPException",
    "ASGIAdminNotFound",
]
