import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'interior-html-modeling/scripts/engine/python'))
from bootstrap import ensure_runtime
ensure_runtime()
if len(sys.argv)>1 and sys.argv[1]=='capture':
 from render import render_shots
 p=argparse.ArgumentParser();p.add_argument('command');p.add_argument('scene');p.add_argument('cameras');p.add_argument('--out',required=True);p.add_argument('--shots');p.add_argument('--mode',choices=['pbr','clay'],default='pbr');p.add_argument('--overwrite',action='store_true');p.add_argument('--reference-mode',choices=['furnished','empty-slots'],default='furnished');p.add_argument('--white-model-requested',action='store_true');a=p.parse_args()
 result=render_shots(a.scene,a.cameras,a.out,a.shots,True,a.mode,a.overwrite,a.reference_mode,a.white_model_requested);print(json.dumps(result,ensure_ascii=False));raise SystemExit(0 if result['complete'] else 2)
from cli import main
raise SystemExit(main('camera'))
