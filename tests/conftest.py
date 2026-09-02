import sys
from pathlib import Path

# Ensure the project root is importable when tests run from a source checkout.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
