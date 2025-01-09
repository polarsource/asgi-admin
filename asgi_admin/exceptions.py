class ASGIAdminErrors(Exception):
    """
    Base class for all exceptions raised by ASGI Admin.

    Parameters:
        message: The error message.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class ASGIAdminConfigurationError(ASGIAdminErrors):
    """
    Base class for all configuration exceptions raised by ASGI Admin.

    Parameters:
        message: The error message.
    """


__all__ = [
    "ASGIAdminErrors",
    "ASGIAdminConfigurationError",
]
