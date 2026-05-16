"""
Routers package.

Having an explicit package (with __init__.py) avoids Python namespace-package edge cases
on Windows/reload where different module resolution can occur.
"""

from . import agent, tickets, tools, flows  # noqa: F401

