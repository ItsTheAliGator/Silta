"""Silta package exposing core client/server utilities.

Avoid importing the CLI from here to prevent side effects and to allow
``python -m silta`` execution without runpy warnings.
"""

from .client import FlowClient
from .server import FlowServer

__all__ = ["FlowClient", "FlowServer"]
