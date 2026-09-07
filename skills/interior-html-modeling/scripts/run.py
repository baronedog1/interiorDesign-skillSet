import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'engine/python'))
from bootstrap import ensure_runtime
ensure_runtime()
from cli import main
raise SystemExit(main('model'))
