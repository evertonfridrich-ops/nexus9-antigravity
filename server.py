"""Source checkout launcher; the installer uses python -m nexus9.server."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from nexus9.server import main

if __name__ == "__main__":
    main()
