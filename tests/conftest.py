"""
Shared test fixtures and configuration for federated-learning-flamby-ehr test suite.
"""
import os
import sys
from pathlib import Path

# Ensure the project root is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set a deterministic test audit key before importing any project modules
os.environ.setdefault("AUDIT_SECRET_KEY", "test-audit-secret-key-for-pytest-suite-2026")
