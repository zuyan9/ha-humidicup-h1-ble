"""Pytest configuration for testing h1lib without Home Assistant dependencies."""

import sys
from pathlib import Path
from types import ModuleType

# Create minimal stub modules for custom_components and humidicup_h1 - This prevents
# their __init__.py files from being executed
custom_components = ModuleType("custom_components")
custom_components.__path__ = []
sys.modules["custom_components"] = custom_components

humidicup_h1 = ModuleType("custom_components.humidicup_h1")
humidicup_h1.__path__ = [
    str(Path(__file__).parents[1] / "custom_components" / "humidicup_h1")
]
sys.modules["custom_components.humidicup_h1"] = humidicup_h1

custom_components.humidicup_h1 = humidicup_h1
