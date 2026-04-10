# core/scratchpad package
"""
Agentic Development Platform - Scratchpad Package

Exposes the ScratchpadManager and utilities for structured, project‑scoped
task memory that agents can use across iterations.

This layer keeps the scratchpad abstraction generic so that agents depend
only on the interface, not on how it is implemented (DIP).[web:234][web:253]
"""

from core.scratchpad.scratchpad_manager import ScratchpadManager, ScratchpadSection
from core.scratchpad.templates import TASK_TEMPLATE

__all__ = [
    "ScratchpadManager",
    "ScratchpadSection",
    "TASK_TEMPLATE",
]
