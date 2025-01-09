import re


def class_name_to_url_path(name: str) -> str:
    """
    Turns a Python class name into a string suitable to be used in URL path.

    Example:
        >>> class_name_to_url_path("MyModel")
        "my-model"
    """
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()


__all__ = [
    "class_name_to_url_path",
]
