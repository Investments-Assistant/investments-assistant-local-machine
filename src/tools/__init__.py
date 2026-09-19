"""Investment assistant tool registry."""

from src.tools.dispatcher import dispatch_tool
from src.tools.definitions import TOOL_DEFINITIONS

__all__ = ["TOOL_DEFINITIONS", "dispatch_tool"]
