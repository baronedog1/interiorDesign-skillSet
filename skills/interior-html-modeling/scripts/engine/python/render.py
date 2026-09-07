"""Render frozen cameras through the same offline HTML. Per-shot atomic persistence and resume.
AI enhancement is an explicit external handoff, not a pretend image-provider implementation.
"""
from __future__ import annotations
import base64,json,os,shutil,sys
from pathlib import Path
from cameras import validate_plan
from common import read,write,atomic_bytes,digest,file_sha,SHARED,require_schema

def open_browser(playwright):
    executable=os.environ.get('INTERIOR_CHROMIUM') or shutil.which('chromium') or shutil.which('google-chrome') or shutil.which('msedge')
    args=[]
    if sys.platform.startswith('linux'):args+=['--disable-dev-shm-usage','--no-sandbox']
    # SSH/service sessions on Windows do not reliably expose the desktop D3D
    # context. Use a deterministic software WebGL backend only in this isolated
    # offline capture browser; leave the user's interactive browser untouched.
    backend=os.environ.get('INTERIOR_HEADLESS_RENDERER','swiftshader')
    if backend=='swiftshader':args+=['--use-angle=swiftshader','--enable-unsafe-swiftshader']
    elif backend!='hardware':raise ValueError('INTERIOR_HEADLESS_RENDERER must be swiftshader or hardware')
    return playwright.chromium.launch(**({'executable_path':executable} if executable else {}),headless=True,args=args)

def load_scene(scene_path):
    path=Path(scene_path).resolve();scene=read(path)
    if scene.get('schema')!='interior.scene/1':raise ValueError('Expected interior.scene/1')
    if digest(scene['layout'])!=scene['layoutHash']:raise ValueError('scene 内嵌布局摘要不匹配')
    html=(path.parent/scene['htmlFile']).resolve()
    if not html.is_relative_to(path.parent):raise ValueError('htmlFile must stay in the project folder')
    if file_sha(html)!=scene['htmlSha256']:raise ValueError('HTML 被更改。请重新建模并生成对应场景清单。')
    if (path.parent/scene['layoutFile']).exists() and digest(read(path.parent/scene['layoutFile']))!=scene['layoutHash']:raise ValueError('layout 已更新但模型未重编译')
    return scene,html

def render_shots(scene_path,cameras_path,out_dir,ids=None,include_review=False,mode='pbr',overwrite=False,reference_mode='furnished',white_model_requested=False):
    from playwright.sync_api import sync_playwright
    scene,html=load_scene(scene_path);plan=read(cameras_path);validate_plan(plan,scene)
    if reference_mode not in ['furnished','empty-slots']:raise ValueError('Unknown reference mode')
    if reference_mode=='empty-slots' and not white_model_requested:raise ValueError('Empty slots require an explicit user request for white-model rendering')
    if plan['sceneKey']!=scene['sceneKey'] or plan['layoutHash']!=scene['layoutHash']:raise ValueError('相机对应的场景版本已过期；不允许悄悄继续')
    chosen=set(ids.split(',')) if isinstance(ids,str) and ids else set(ids or [])
    if chosen-set(s['id'] for s in plan['shots']):raise ValueError('Requested shot ID does not exist')
    shots=[s for s in plan['shots'] if not chosen or s['id'] in chosen];out=Path(out_dir);out.mkdir(parents=True,exist_ok=True);manifest_path=out/'renders.json'
    old=read(manifest_path) if manifest_path.exists() else None
    manifest={'schema':'interior.renders/1','sceneKey':scene['sceneKey'],'layoutHash':scene['layoutHash'],'sourceType':'webgl','results':[]}
    if old and old.get('sceneKey')==scene['sceneKey']:manifest['results']=old.get('results',[])
    saved={x['shotId']:x for x in manifest['results']};work=[];skipped=[]
    for s in shots:
        # Capture every selected, technically valid candidate. Quality is an observation,
        # not a reason to suppress an image that the Agent needs to inspect.
        key=digest({'sceneKey':scene['sceneKey'],'camera':s,'mode':mode,'referenceMode':reference_mode});old=saved.get(s['id']);file=out/(s['id']+'.png')
        if not overwrite and old and old.get('inputKey')==key and old.get('status') in ['rendered','needs-review'] and file.exists() and file_sha(file)==old.get('sha256'):continue
        work.append((s,key,file))
    if work:
        with sync_playwright() as p:
            browser=open_browser(p);page=browser.new_page(viewport={'width':1280,'height':800},device_scale_factor=1);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            try:
                # A synthetic about:blank canvas may report no WebGL on Windows
                # even when the real file origin runs correctly. Test the actual
                # model, not an unrelated preflight context.
                page.goto(html.as_uri(),wait_until='load',timeout=180000)
                page.wait_for_function('window.__CREAM_READY__===true || document.querySelector("#load-note")?.textContent.startsWith("加载失败：")',timeout=120000)
                if not page.evaluate('window.__CREAM_READY__===true'):raise RuntimeError(page.locator('#load-note').inner_text())
                for shot,key,file in work:
                    row={'shotId':shot['id'],'inputKey':key,'cameraDigest':digest(shot),'sourceType':'webgl','mode':mode,'image':file.name,'status':'failed','providerRequestId':None}
                    try:
                        data=page.evaluate('(x)=>CREAM.captureFrame(x.shot,x.mode,x.options)',{'shot':shot,'mode':mode,'options':{'referenceMode':reference_mode,'whiteModelRequested':white_model_requested}})
                        if data.get('referenceMode','furnished')!=reference_mode:raise ValueError('This model runtime does not support the requested reference mode; rebuild the same JSON')
                        if data['sceneKey']!=scene['sceneKey']:raise ValueError('HTML runtime sceneKey does not match scene.json')
                        if errors:raise RuntimeError('; '.join(errors))
                        image=base64.b64decode(data['dataUrl'].split(',',1)[1]);atomic_bytes(file,image)
                        review=data['review'];low=any(x['sampledClearRatio']<.5 for x in review)
                        row.update({'sha256':file_sha(file),'width':data['width'],'height':data['height'],'status':'needs-review' if low or shot['status']=='review' else 'rendered','visibilitySamples':review,'note':'27点射线抽检是遮挡预警，不是逐像素视觉验收。'})
                        row.update(referenceMode=reference_mode,hiddenPlacementIds=data.get('hiddenPlacementIds',[]),whiteModelRequested=white_model_requested if reference_mode=='empty-slots' else False)
                    except Exception as exc:row['error']=str(exc)
                    saved[shot['id']]=row;manifest['results']=list(saved.values());manifest['skipped']=skipped;write(manifest_path,manifest)
            finally:browser.close()
    manifest['results']=list(saved.values());manifest['skipped']=skipped;manifest['executedThisRun']=len(work);manifest['complete']=all(x['status']!='failed' for x in manifest['results']) and not skipped;write(manifest_path,manifest);return manifest

def ai_request(scene_path,cameras_path,renders_path,shot_id,out_file,style=None,product_refs=None,reference_mode='furnished',white_model_requested=False):
    scene,_=load_scene(scene_path);plan=read(cameras_path);validate_plan(plan,scene);renders=read(renders_path)
    if plan['sceneKey']!=scene['sceneKey'] or renders.get('sceneKey')!=scene['sceneKey']:raise ValueError('场景/相机/截图不是同一版本')
    shot=next((s for s in plan['shots'] if s['id']==shot_id),None);row=next((x for x in renders.get('results',[]) if x['shotId']==shot_id),None)
    if not shot or not row or row.get('status') not in ['rendered','needs-review']:raise ValueError('先生成同机位完整模型截图；不能拿空图或占位图发请求')
    if reference_mode not in ['furnished','empty-slots']:raise ValueError('Unknown reference mode')
    if reference_mode=='empty-slots' and not white_model_requested:raise ValueError('White-model rendering must be explicitly requested by the user')
    if row.get('referenceMode','furnished')!=reference_mode:raise ValueError('Reference screenshot mode does not match requested rendering mode')
    if row.get('cameraDigest')!=digest(shot):raise ValueError('截图不是当前相机参数生成；请重渲染该镜头')
    image=(Path(renders_path).resolve().parent/row['image']).resolve()
    if not image.is_relative_to(Path(renders_path).resolve().parent):raise ValueError('截图路径越出 renders 文件夹')
    if file_sha(image)!=row.get('sha256'):raise ValueError('源截图摘要不匹配')
    presets=read(SHARED/'catalog/styles.json');style_record=scene['layout'].get('customStyle') or next(x for x in presets['styles'] if x['id']==scene['layout']['styleId']);style_text=style or style_record['renderBrief']
    subjects=[{'id':p['id'],'name':p['name'],'componentId':p['componentId'],'sizeMetres':p['size'],'rotationDegrees':p['rotationY']} for p in scene['layout']['placements'] if p['id'] in shot['subjectIds']]
    slots=[{k:p[k] for k in ['id','componentId','roomId','position','size','rotationY']} for p in scene['layout']['placements']]
    if reference_mode=='empty-slots' and set(row.get('hiddenPlacementIds',[]))!=set(p['id'] for p in slots):raise ValueError('Empty reference must preserve all placement slots while hiding their visual instances')
    text='保持截图的房型、结构、墙体、门窗位置、空间尺度完全不变；相机位置、朝向、透视/正交方式、视野和裁切与截图一致，不扩房、不移墙、不增减门窗。\n'
    text+='默认完整场景模式：截图包含全部活动家具、柜体及已有细节。把未指定品牌资产的简化家具细化为精细家具，保持类别、数量、位置、朝向及尺寸包络。\n' if reference_mode=='furnished' else '用户明确选择空白槽位/白模模式：截图只隐藏 placements 中家具与柜体的可见实例，建筑结构不变。依据原 JSON 槽位逐一放入精细家具，不能自行重做布局，不能将空房理解为任意摆放。\n'
    text+='指定资产优先于风格自由发挥：保留其外形、结构、部件数量、颜色纹理和长宽高比例，不拉伸、不压扁、不变形；按真实尺寸及槽位大小匹配。尺寸冲突应说明并回源调整，不能扭曲指定资产塞入。提升材质、纹理尺度、光线与接触阴影，不改变机位。\n风格：'+style_text+'\n槽位来自当前原 JSON，米制，position=[x,y,z]，size=[宽,高,深]，rotationY=度：\n'+json.dumps(slots,ensure_ascii=False)
    refs=[]
    for binding in product_refs or []:
        path=Path(binding['path']).resolve();id=binding['placementId']
        if id not in [p['id'] for p in scene['layout']['placements']]:raise ValueError('产品参考未绑定到现有 placementId')
        if not path.is_file():raise ValueError('产品参考不存在')
        size=binding.get('sizeMetres')
        if size is not None:
            import math
            if not isinstance(size,list) or len(size)!=3 or not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and v>0 for v in size):raise ValueError('Asset sizeMetres must be three positive finite dimensions in metres')
        refs.append({'placementId':id,'path':str(path),'sha256':file_sha(path),'sizeMetres':size,'sizeSource':'specified-asset' if size else 'unknown-do-not-invent','preserveIdentity':True})
    text+='\n指定资产绑定及真实尺寸（null 表示未知，不得把槽位尺寸冒称产品实测；应读取资产元数据或请用户补充）：\n'+json.dumps([{k:v for k,v in r.items() if k not in ['path','sha256']} for r in refs],ensure_ascii=False)
    request={'schema':'interior.ai-request/1','status':'prepared-not-generated','sceneKey':scene['sceneKey'],'shotId':shot_id,'cameraDigest':digest(shot),'source':{'path':str(image),'sha256':row['sha256'],'role':'complete-model-frame'},'prompt':text.strip(),'subjects':subjects,'productReferences':refs,'requiredReview':['structure','openings','furnitureLayout','camera'],'generation':None,'note':'此文件是实际调用图像工具的输入，不是生成完成回执。风格参考不能覆盖结构。'}
    request.update(referenceMode=reference_mode,whiteModelRequested=white_model_requested if reference_mode=='empty-slots' else False,placementSlots=slots)
    request['source']['role']='complete-model-frame' if reference_mode=='furnished' else 'empty-slot-architecture-frame'
    request['requiredReview']+=['furnitureDetail','assetIdentity','assetScale']
    write(out_file,request);atomic_bytes(Path(out_file).with_suffix('.prompt.txt'),text.strip().encode('utf-8'));return request

def ai_result(request_path,image_path,review_path,out_file):
    request=read(request_path);review=read(review_path);image=Path(image_path)
    if request.get('schema')!='interior.ai-request/1':raise ValueError('Invalid AI request')
    if file_sha(request['source']['path'])!=request['source']['sha256']:raise ValueError('Input changed after AI request was prepared')
    if file_sha(image)==request['source']['sha256']:raise ValueError('输出与输入是同一文件内容，不能登记为 AI 已生成')
    for key in request['requiredReview']:
        if review.get(key) not in ['pass','fail']:raise ValueError('Review missing pass/fail field: '+key)
    from PIL import Image
    with Image.open(image) as im:im.verify()
    artifact={'schema':'interior.ai-result/1','sourceType':'ai-generated','sceneKey':request['sceneKey'],'shotId':request['shotId'],'status':'accepted' if all(review[k]=='pass' for k in request['requiredReview']) else 'delivered-with-observations','requestDigest':digest(request),'image':str(image.resolve()),'sha256':file_sha(image),'review':review,'providerRequestId':review.get('providerRequestId'),'note':'结果由外部图像工具生成；此命令只核对文件与登记真实人工/视觉复核。'};write(out_file,artifact);return artifact
