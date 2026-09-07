import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'interior-html-modeling/scripts/engine/python'))
os.environ.setdefault('IDK_ENV_FILE',str(Path(__file__).resolve().parents[1]/'.runtime/baiende-platform.env'))
os.environ.setdefault('IDK_TOOL_NAME','idk-canvas-ingest-agent')
from platform_bridge import main
raise SystemExit(main())
