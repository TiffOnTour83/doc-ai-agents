"""Doc Logic — AI document structuring system.

A staged pipeline of single-responsibility agents:
Extractor -> Schema Suggester -> (human approval gate) -> Harmonizer -> Auditor.

Deterministic and transparent by default; read-only toward source documents.
"""

__version__ = "1.0.0"
PIPELINE = ["extract", "suggest", "gate", "harmonize", "audit"]
