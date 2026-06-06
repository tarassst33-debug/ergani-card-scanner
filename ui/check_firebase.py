#!/usr/bin/env python3
"""Test Firestore connection for projectcar-7846b."""

from __future__ import annotations

import sys
from pathlib import Path

UI_DIR = Path(__file__).resolve().parent
if str(UI_DIR) not in sys.path:
    sys.path.insert(0, str(UI_DIR))

from firebase_db import ping_firestore  # noqa: E402


def main() -> int:
    try:
        info = ping_firestore()
        print("Σύνδεση Firestore OK:", info)
        return 0
    except Exception as exc:
        print("Αποτυχία σύνδεσης:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
