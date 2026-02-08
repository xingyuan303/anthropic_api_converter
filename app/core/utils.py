"""
Utility functions for the application.
"""


def mask_api_key(api_key: str) -> str:
    """
    Mask an API key for safe logging.

    Shows only the last 4 characters to help identify the key
    while protecting the full value from exposure.

    Args:
        api_key: The API key to mask

    Returns:
        Masked API key string (e.g., "sk-***ABCD")

    Examples:
        >>> mask_api_key("sk-1234567890abcdef")
        'sk-***cdef'
        >>> mask_api_key("short")
        '***'
    """
    if not api_key:
        return "***"

    if len(api_key) <= 7:
        # Too short, mask completely
        return "***"

    # Show prefix (sk-) and last 4 characters
    if api_key.startswith("sk-"):
        return f"sk-***{api_key[-4:]}"
    else:
        # Non-standard format, just show last 4
        return f"***{api_key[-4:]}"
