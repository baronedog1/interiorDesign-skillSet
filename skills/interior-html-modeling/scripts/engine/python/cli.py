"""Shared routing for model, camera and native-image preparation; platform has its own entry."""
from __future__ import annotations
import argparse,os,shutil,subprocess,sys,json
from pathlib import Path
from common import read,write

def main(stage):
    p=argparse.ArgumentParser(description={'model':'JSON 到稳定 Three.js HTML','camera':'保留预设并补正视机位','render':'原生绘图任务准备与真实结果登记'}[stage]);sub=p.add_subparsers(dest='command',required=True)
    if stage=='model':
        build=sub.add_parser('build');build.add_argument('layout');build.add_argument('--out',required=True);build.add_argument('--presets');build.add_argument('--style')
        for cmd in ['style-check','style-add']:
            item=sub.add_parser(cmd);item.add_argument('recipe')
        item=sub.add_parser('style-resolve');item.add_argument('query');item.add_argument('--out')
        item=sub.add_parser('style-evidence');item.add_argument('recipe')
        item=sub.add_parser('asset-bundle');item.add_argument('index');item.add_argument('--out',required=True)
        item=sub.add_parser('import-html');item.add_argument('html');item.add_argument('--out',required=True)
        item=sub.add_parser('placement-check');item.add_argument('layout');item.add_argument('--id',required=True)
    elif stage=='camera':
        find=sub.add_parser('find');find.add_argument('scene');find.add_argument('--out',required=True);find.add_argument('--width',type=int,default=1280);find.add_argument('--height',type=int,default=960);find.add_argument('--presets-only',action='store_true')
        apply=sub.add_parser('apply');apply.add_argument('scene');apply.add_argument('cameras');apply.add_argument('--out',required=True)
    else:
        req=sub.add_parser('ai-request');req.add_argument('scene');req.add_argument('cameras');req.add_argument('renders');req.add_argument('--shot',required=True);req.add_argument('--out',required=True);req.add_argument('--style');req.add_argument('--products',help='JSON list: [{placementId, path}]')
        req.add_argument('--reference-mode',choices=['furnished','empty-slots'],default='furnished');req.add_argument('--white-model-requested',action='store_true')
        req.add_argument('--anchor-result',help='Reviewed first view result of the same open-space/style series')
        req.add_argument('--design-brief',help='JSON with common/spaces design intent and styleReferences images')
        native=sub.add_parser('native-prepare');native.add_argument('request');native.add_argument('capabilities');native.add_argument('--out',required=True)
        native=sub.add_parser('native-result');native.add_argument('job');native.add_argument('image');native.add_argument('invocation');native.add_argument('review');native.add_argument('--out',required=True)
        native=sub.add_parser('native-start');native.add_argument('job');native.add_argument('--out',required=True)
        native=sub.add_parser('native-complete');native.add_argument('invocation');native.add_argument('image');native.add_argument('--out',required=True)
    a=p.parse_args()
    try:
        if stage=='model' and a.command in ['style-resolve','style-evidence']:
            from styles import resolve_style,check_evidence
            r=resolve_style(a.query) if a.command=='style-resolve' else check_evidence(read(a.recipe))
            if getattr(a,'out',None):write(a.out,r)
        elif stage=='model' and a.command in ['asset-bundle','import-html','placement-check']:
            from native import bundle_library,import_html,audit_placement
            r=bundle_library(a.index,a.out) if a.command=='asset-bundle' else import_html(a.html,a.out) if a.command=='import-html' else audit_placement(a.layout,a.id)
        elif stage=='model' and a.command in ['style-check','style-add']:
            from styles import validate_style,add_style
            r=validate_style(read(a.recipe)) if a.command=='style-check' else add_style(a.recipe)
        elif stage=='model':
            from model import build_model
            scene=build_model(a.layout,a.out,a.presets,a.style);r={'ok':True,'sceneKey':scene['sceneKey'],'html':str(Path(a.out)/'model.html'),'scene':str(Path(a.out)/'scene.json')}
        elif stage=='camera' and a.command=='find':
            from render import load_scene
            from cameras import compile_cameras
            scene,_=load_scene(a.scene);r=compile_cameras(scene,{'width':a.width,'height':a.height},not a.presets_only);write(a.out,r);r={'ok':True,'shots':len(r['shots']),'ready':sum(x['status']=='ready' for x in r['shots']),'review':sum(x['status']=='review' for x in r['shots']),'output':a.out}
        elif stage=='camera':
            from render import load_scene
            from common import require_schema,atomic_bytes
            from model import js_json
            scene,html=load_scene(a.scene);cameras=read(a.cameras)
            from cameras import validate_plan
            validate_plan(cameras,scene)
            if Path(a.out).resolve()==html:raise ValueError('审阅页不能覆盖绑定的原 model.html；请选择新的文件名')
            if cameras['sceneKey']!=scene['sceneKey']:raise ValueError('相机不属于此场景')
            # A review copy adds camera data before boot, not a second event-bound script.
            text=html.read_text(encoding='utf-8-sig');token='window.PREVIEW_PRESETS=';start=text.index(token)+len(token);end=text.index(';window.SCENE_KEY=',start)
            presets=dict(scene['presets']);
            for s in cameras['shots']:
                if s['projection']=='perspective':presets[s['id']]={'title':s['name']+('（需复核）' if s['status']!='ready' else ''),'pos':s['position'],'target':s['target'],'fov':s['fov'],'verticalShift':s.get('verticalShift',0.),'near':s.get('near',.04)}
            text=text[:start]+js_json(presets)+text[end:];atomic_bytes(a.out,text.encode());r={'ok':True,'reviewHtml':a.out,'note':'相机审阅副本；正式渲染仍读取 scene.json 绑定的原模型和 cameras.json，勿覆盖源 model.html。'}
        elif a.command in ['native-start','native-complete']:
            from native_image import start,complete
            r=start(a.job,a.out) if a.command=='native-start' else complete(a.invocation,a.image,a.out)
        elif a.command in ['native-prepare','native-result']:
            from native_image import prepare,finish
            r=prepare(a.request,a.capabilities,a.out) if a.command=='native-prepare' else finish(a.job,a.image,a.invocation,a.review,a.out)
        elif a.command=='ai-request':
            from render import ai_request
            r=ai_request(a.scene,a.cameras,a.renders,a.shot,a.out,a.style,read(a.products) if a.products else None,a.reference_mode,a.white_model_requested,a.anchor_result,read(a.design_brief) if a.design_brief else None)
        else:raise ValueError('Unsupported command')
        print(json.dumps(r,ensure_ascii=False,indent=2));return 0 if r.get('ok',True) and not any(x.get('status')=='failed' for x in r.get('results',[])) else 2
    except Exception as e:
        print(json.dumps({'ok':False,'error':str(e)},ensure_ascii=False),file=sys.stderr);return 2
