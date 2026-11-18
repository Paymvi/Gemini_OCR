import sys
from pathlib import Path

# Let tests import the app modules (pipeline, spreadsheet, ...) from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
