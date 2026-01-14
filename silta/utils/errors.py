class ConnectionError(Exception):
    """Raised when the client cannot communicate with the server."""


class DependencyError(RuntimeError):
    """Raised when an optional runtime dependency is missing."""
