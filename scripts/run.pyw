"""pythonw launcher for a source checkout; no persistent console window."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from dev_storage_manager.__main__ import main

sys.exit(main())
