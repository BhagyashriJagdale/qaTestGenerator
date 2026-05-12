"""
pytest configuration — mocks heavy optional dependencies so tests run without
GPU, ChromaDB, or LLM API keys.
"""

import sys
import os
from unittest.mock import MagicMock

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Stub heavy optional dependencies before any test module imports them
for mod in ("chromadb", "sentence_transformers", "torch", "transformers"):
    sys.modules.setdefault(mod, MagicMock())
