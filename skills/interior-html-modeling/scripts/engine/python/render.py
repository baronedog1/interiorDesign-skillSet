"""Render frozen cameras through the same offline HTML. Per-shot atomic persistence and resume.
AI enhancement is an explicit external handoff, not a pretend image-provider implementation.
"""
from __future__ import annotations
import base64,json,os,shutil,sys,time
from pathlib import Path
from cameras import validate_plan
from common import read,write,atomic_bytes,digest,file_sha,SHARED,require_schema
from timing import traced,span,now

REFERENCE_POLICY='shell-layout-design-space-v4'

def image_slot_anchors(placements,shot):
    """Project placement boxes through the actual frozen camera; no layout edits.
    Rectangles are approximate projections, not visible masks or product outlines.
    Clip crossing box edges against the near plane before perspective division.
    """
    import math,numpy as np
    from cameras import basis,corners
    f,r,u=basis(shot['position'],shot['target'],shot['up']);aspect=shot['frame']['width']/shot['frame']['height'];out=[]
    for p in placements:
        delta=np.asarray(corners(p))-np.asarray(shot['position']);v=np.column_stack((delta@r,delta@u,delta@f));points=[q for q in v if q[2]>=.04]
        for i in range(8):
            for bit in [1,2,4]:
                j=i^bit
                if j>i and (v[i,2]-.04)*(v[j,2]-.04)<0:
                    points.append(v[i]+(v[j]-v[i])*(.04-v[i,2])/(v[j,2]-v[i,2]))
        if not points:continue
        a=np.asarray(points)
        if shot['projection']=='orthographic':xy=a[:,:2]/np.asarray([shot['orthographicSpan']*aspect/2,shot['orthographicSpan']/2])
        else:
            t=math.tan(math.radians(shot['fov'])/2);xy=a[:,:2]/(a[:,2,None]*np.asarray([t*aspect,t]));xy[:,1]-=shot.get('verticalShift',0)
        xy=np.column_stack(((xy[:,0]+1)/2,(1-xy[:,1])/2));lo=xy.min(axis=0);hi=xy.max(axis=0)
        if np.any(hi<0) or np.any(lo>1):continue
        yaw=math.radians(p['rotationY']);front=np.asarray([math.sin(yaw),0,math.cos(yaw)])
        relative_yaw=round(math.degrees(math.atan2(float(front@r),float(front@(-f)))),2) if abs(float(f[1]))<.99 else None
        out.append({**{k:p[k]for k in ['id','componentId','roomId','position','size','rotationY']},'cameraRelativeYawDegrees':relative_yaw,'imageBounds01':[np.clip(lo,0,1).round(5).tolist(),np.clip(hi,0,1).round(5).tolist()],'imageBoundsUnclipped01':[lo.round(5).tolist(),hi.round(5).tolist()],'partlyOutsideFrame':bool(np.any(lo<0)or np.any(hi>1)),'projectionOnlyNotVisibility':True})
    return out

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

@traced('camera.capture-batch')
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
        key=digest({'sceneKey':scene['sceneKey'],'camera':s,'mode':mode,'referenceMode':reference_mode,'layoutReferenceVersion':3});old=saved.get(s['id']);file=out/(s['id']+'.png')
        pair=(old or {}).get('layoutReference',{});pair_file=out/(s['id']+'.layout.png')
        pair_current=reference_mode!='empty-slots' or (pair.get('image')==pair_file.name and pair_file.is_file() and file_sha(pair_file)==pair.get('sha256'))
        if not overwrite and old and pair_current and old.get('inputKey')==key and old.get('status') in ['rendered','needs-review'] and file.exists() and file_sha(file)==old.get('sha256'):continue
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
                    started=now();clock=time.perf_counter()
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
                        row['visiblePlacementIds']=data.get('visiblePlacementIds')
                        row['spaceContext']=data.get('spaceContext')
                        if reference_mode=='empty-slots':
                            # The empty frame describes architecture, not furniture geometry.
                            # Capture a separate same-camera spatial reference in the same
                            # browser. It is never a furniture-identity or lighting source.
                            layout=page.evaluate('(x)=>CREAM.captureFrame(x.shot,x.mode,{referenceMode:"furnished"})',{'shot':shot,'mode':mode})
                            if errors:raise RuntimeError('; '.join(errors))
                            if layout['sceneKey']!=scene['sceneKey'] or (layout['width'],layout['height'])!=(data['width'],data['height']):raise ValueError('Paired capture scene/frame mismatch')
                            layout_file=out/(shot['id']+'.layout.png')
                            atomic_bytes(layout_file,base64.b64decode(layout['dataUrl'].split(',',1)[1]))
                            row['layoutReference']={'image':layout_file.name,'sha256':file_sha(layout_file),'cameraDigest':digest(shot),'sceneKey':scene['sceneKey'],'role':'same-camera-layout-only'}
                            row['visiblePlacementIds']=layout.get('visiblePlacementIds')
                            row['spaceContext']=layout.get('spaceContext')
                        row['visibilityMethod']='in-frame-surface-ray-samples-not-pixel-proof' if isinstance(row.get('visiblePlacementIds'),list) else 'legacy-room-group'
                    except Exception as exc:row.update(status='failed',error=str(exc))
                    row['timing']={'startedAt':started,'finishedAt':now(),'elapsedMs':round((time.perf_counter()-clock)*1000,3),'kind':'code','scope':'capture-and-save-one-shot'}
                    saved[shot['id']]=row;manifest['results']=list(saved.values());manifest['skipped']=skipped;write(manifest_path,manifest)
            finally:browser.close()
    manifest['results']=list(saved.values());manifest['skipped']=skipped;manifest['executedThisRun']=len(work);manifest['complete']=all(x['status']!='failed' for x in manifest['results']) and not skipped;write(manifest_path,manifest);return manifest

@traced('render.prepare-request')
def ai_request(scene_path,cameras_path,renders_path,shot_id,out_file,style=None,product_refs=None,reference_mode='furnished',white_model_requested=False,anchor_result=None,design_brief=None):
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
    group={shot['roomId']} if shot['roomId'] else set()
    while True:
        expanded=set(group)
        for connection in scene['layout'].get('openConnections',[]):
            if group.intersection(connection['rooms']):expanded.update(connection['rooms'])
        if expanded==group:break
        group=expanded
    visible_ids=row.get('visiblePlacementIds')
    candidates=[p for p in scene['layout']['placements']if p['id']in visible_ids] if isinstance(visible_ids,list) else [p for p in scene['layout']['placements']if p['roomId']in group]
    image_slots=image_slot_anchors(candidates,shot)
    prompt_slots=[{k:v for k,v in p.items()if k not in ['position','rotationY','roomId']}for p in image_slots]
    if reference_mode=='empty-slots' and set(row.get('hiddenPlacementIds',[]))!=set(p['id'] for p in slots):raise ValueError('Empty reference must preserve all placement slots while hiding their visual instances')
    text='保持截图的房型、结构、墙体、门窗位置、空间尺度完全不变；相机位置、朝向、透视/正交方式、视野和裁切与截图一致，不扩房、不移墙、不增减门窗。\n'
    text+='默认完整粗模截图：图中普通家具是占位示意，不是款式、细部比例、工艺或光照的参考；不要复制其方块、厚底座、膨胀软包或低模轮廓。\n' if reference_mode=='furnished' else '用户明确选择空白槽位/白模模式：仅隐藏家具与柜体可见实例，建筑及原 JSON 槽位不变；仍按槽位放置精细家具，不任意重新布局。\n'
    text+='粗模只约束建筑、机位以及家具功能、数量、位置、朝向、约略尺度和通行关系。精细家具应按绑定参考图片的款式重建，再放入相应槽位；锁款锁参考图，不锁粗模造型。普通占位尺寸不是产品实测，更不是要求把参考家具非均匀拉伸到粗模外包盒。\n'
    text+='有产品/精细家具参考图时，保留图中该产品的造型、部件、材质及比例；不保留参考照片的房间、背景或镜头。按真实尺寸适配，尺寸未知时只作有说明的比例意向；尺寸冲突回到选型/布局处理，不变形硬塞。\n'
    text+='没有绑定款式参考且没有该家具的精细定样时，按用户风格设计可信家具工艺，不锁粗模身份；标为概念选型，不声称采购型号。固定的是建筑壳、墙门窗洞口位置尺寸、机位和主要家具功能布局，不是粗模里所有可见细节。门扇、窗框、分格、五金、玻璃与帘可按风格重新设计，但不移动/扩开洞口，不妨碍开合。\n'
    text+='按下述同空间设计意图完成墙面、天花吊顶/收口、吊灯及辅助灯、挂画、器物、织物、绿植与生活布景，围绕主体有层次地选择，不要求每空间都加齐，不增设无需求的隔断柜或大件家具。吊顶在原建筑层高以内形成饰面，不凭空造承重梁；设计灯位不冒称现状电气点位。自然光、灯光、反射及接触阴影重新计算，不照抄粗模照明。窗外可形成符合楼层视线与日光方向的意向景观，不冒称现场实景，不改变窗洞。\n风格：'+style_text+'\n当前画面家具位置与朝向（全部已转换到当前相机，不是户型世界坐标）：size=[宽,高,深]米。cameraRelativeYawDegrees=0表示家具正面朝向观众，±90为侧面，±180为背面；床的正面是从床尾正对床头，不是床侧。不得照搬产品参考照片拍摄角度。imageBounds01左上原点[0,0]、右下[1,1]；imageBoundsUnclipped01为裁切前范围，超出0–1的部分应自然出画，不退镜头把整件收进来。框只参考位置/约略尺度，不是产品轮廓；不拉伸产品填框。投影不是可见性证明，墙后部分保持遮挡，不把画外家具搬入镜头。\n'+json.dumps(prompt_slots,ensure_ascii=False)
    refs=[]
    for binding in product_refs or []:
        path=Path(binding['path']).resolve();id=binding['placementId']
        if id not in [p['id'] for p in scene['layout']['placements']]:raise ValueError('产品参考未绑定到现有 placementId')
        if not path.is_file():raise ValueError('产品参考不存在')
        if file_sha(path)==row['sha256']:raise ValueError('粗模截图不能同时冒充精细家具款式参考')
        size=binding.get('sizeMetres')
        if size is not None:
            import math
            if not isinstance(size,list) or len(size)!=3 or not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and v>0 for v in size):raise ValueError('Asset sizeMetres must be three positive finite dimensions in metres')
        refs.append({'placementId':id,'path':str(path),'sha256':file_sha(path),'sizeMetres':size,'sizeSource':'specified-asset' if size else 'unknown-do-not-invent','preserveIdentity':True,'role':'furniture-identity-reference','identitySource':'reference-image-not-proxy'})
    frame_ids={p['id']for p in image_slots}
    frame_refs=[r for r in refs if r['placementId']in frame_ids]
    text+='\n当前画面产品绑定及真实尺寸（null 表示未知，不得把槽位尺寸冒称产品实测；应读取资产元数据或请用户补充）：\n'+json.dumps([{k:v for k,v in r.items() if k not in ['path','sha256']} for r in frame_refs],ensure_ascii=False)
    request={'schema':'interior.ai-request/1','status':'prepared-not-generated','sceneKey':scene['sceneKey'],'shotId':shot_id,'cameraDigest':digest(shot),'source':{'path':str(image),'sha256':row['sha256'],'role':'complete-model-frame'},'prompt':text.strip(),'subjects':subjects,'productReferences':refs,'requiredReview':['structure','openings','furnitureLayout','camera'],'generation':None,'note':'此文件是实际调用图像工具的输入，不是生成完成回执。风格参考不能覆盖结构。'}
    request.update(referenceMode=reference_mode,whiteModelRequested=white_model_requested if reference_mode=='empty-slots' else False,placementSlots=slots,imageSlotAnchors=image_slots,frameProductReferences=frame_refs,cameraFrame={k:shot[k]for k in ['position','target','up','fov','frame','projection','verticalShift','orthographicSpan']if k in shot},referencePolicy=REFERENCE_POLICY)
    request['layoutReferences']=[]
    if reference_mode=='empty-slots' and row.get('layoutReference'):
        lr=row['layoutReference'];lp=(Path(renders_path).resolve().parent/lr['image']).resolve()
        if not lp.is_relative_to(Path(renders_path).resolve().parent) or lr.get('cameraDigest')!=digest(shot) or lr.get('sceneKey')!=scene['sceneKey'] or file_sha(lp)!=lr['sha256']:raise ValueError('Paired layout reference no longer matches this capture')
        request['layoutReferences']=[{'path':str(lp),'sha256':lr['sha256'],'role':'same-camera-layout-only'}]
        text+='\n附加同机位家具布局示意图只负责家具数量、方向、位置、前后遮挡与自然裁切，不负责款式、工艺、材质和光影。建筑仍以空房主图为准；精细家具身份仍以绑定产品图为准，不照搬产品照片镜头，也不继承布局示意图的粗模造型。它直观表达同一JSON槽位，不是另一套布局。'
    elif reference_mode=='empty-slots':
        request['layoutReferenceObservation']='Historical empty capture has no paired layout image; recapture this frozen camera for the current paired-input method.'
    design=design_brief or {}
    if not isinstance(design,dict):raise ValueError('Design brief must be an object')
    room_design={**design.get('common',{}),**design.get('spaces',{}).get(shot.get('roomId'),{})}
    style_refs=[]
    for ref in design.get('styleReferences',[]):
        p=Path(ref['path']).resolve()
        style_refs.append({'path':str(p),'sha256':file_sha(p),'role':'style-design-reference-not-layout','assetId':ref.get('assetId'),'notes':ref.get('notes','')})
    request.update(designIntent=room_design,styleReferences=style_refs)
    text+='\n全屋共用与本空间设计意图（设计提案，不是现状建筑事实）：\n'+json.dumps(room_design,ensure_ascii=False)
    text+='\n风格参考图只解释配色、硬装语言、家具搭配、布景密度、灯光与摄影品质；不可照搬它的房型、镜头或无需求的屏风/书架。产品参考图仍决定对应产品身份。'
    from PIL import Image
    with Image.open(image) as im:request['sourceFrame']={'width':im.width,'height':im.height,'aspectRatio':im.width/im.height}
    text+=f"\n源画幅 {request['sourceFrame']['width']}×{request['sourceFrame']['height']}，输出保持相同宽高比与裁切，不用拉伸图片冒充同机位。"
    request['source']['role']='complete-model-frame' if reference_mode=='furnished' else 'empty-slot-architecture-frame'
    request['requiredReview']+=['furnitureDetail','assetIdentity','assetScale']
    # Connected open rooms share furniture/CMF identity, but never share camera geometry.
    series_key=digest({'layoutHash':scene['layoutHash'],'style':style_text,'rooms':sorted(group),'mode':reference_mode,'products':[{k:v for k,v in r.items() if k!='path'} for r in refs],'design':{k:v for k,v in design.items() if k!='styleReferences'},'styleReferences':[{k:v for k,v in r.items() if k!='path'} for r in style_refs],'referencePolicy':REFERENCE_POLICY})
    series_path=Path(out_file).resolve().parent/'render-series.json'
    registry=read(series_path) if series_path.exists() else {}
    prior=anchor_result or registry.get(series_key,{}).get('resultPath')
    request.update(roomId=shot['roomId'],consistencyGroup=sorted(group),seriesKey=series_key,seriesPath=str(series_path),styleBrief=style_text,consistencyReferences=[])
    if prior:
        previous=read(prior)
        if previous.get('seriesKey')!=series_key or previous.get('status')!='accepted':raise ValueError('Anchor must be a visually reviewed result from this same space/style series')
        if file_sha(previous['image'])!=previous['sha256']:raise ValueError('Anchor image changed; use its actual current result')
        request['consistencyReferences']=[{'path':previous['image'],'sha256':previous['sha256'],'role':'same-space-appearance-only','shotId':previous['shotId']}]
        text+='\n同空间精细定样图已经提供：只沿用其中可见家具的精细款式、形体与CMF，不回退粗模造型；本次建筑与镜头以第一张粗模截图为准。绑定产品参考优先于定样；定样中不可见的家具不能声称已锁款。同一日景系列的光源保持物理一致，但按当前视角重新计算光影，不复制上一张的阴影图案。'
    else:
        text+='\n这是该空间/风格的首张精细定样。绑定参考图决定对应家具款式；其余家具重新设计为真实精细产品，不照抄粗模。后续同空间机位再以本张精细图统一外观。'
    from native_image import references
    attached=references(request)
    request['referenceGuide']=[{'imageIndex':i+1,'role':r['role'],'placementIds':r.get('placementIds',[])} for i,r in enumerate(attached)]
    text+='\n实际附图顺序与职责（图片编号从1起）：\n'+json.dumps(request['referenceGuide'],ensure_ascii=False)
    request['requiredReview']+=['crossViewConsistency']
    context=row.get('spaceContext')
    if context:
        request['spaceContext']=context
        text+='\n空间与连接事实（来自同一模型及本机位射线，不从粗模外观猜房间）：'+json.dumps(context,ensure_ascii=False)
        text+='\n当前空间、可见邻接空间及门后的目标必须与上述身份一致；阳台不是卧室，厨房不是普通房间。可见门洞不等于门后整间都入画。保持墙洞和隔断类别、门扇开合、玻璃透明/磨砂/实板性质；款式细节可精细化，但不得把关闭实门画成敞口、玻璃移门画成实墙。向外的目标为unknown时不擅自认定直通户外或另一间房；户外景观只能按已知朝向和设计意图演绎并标明非现场实景。主图保留当前截图已有天花与地面，不裁掉吊灯、吊顶或地面，不为精细家具改镜头。'
    else:
        request['spaceContextStatus']='legacy-capture-missing; recapture-for-current-task'
    if shot.get('near'):
        text+='\n本图为狭窄房间的虚拟正视后退机位，近裁切只为看全主体，并不表示拆墙或改变房型；沿用当前画面，不能补画镜头前被剖切的遮挡墙。必须保留完整床头、床尾、左右床边及现有地面天花。精细床按原位置朝向和尺度替换，不缩床、不重新裁图。'
    request['prompt']=text.strip()
    write(out_file,request);atomic_bytes(Path(out_file).with_suffix('.prompt.txt'),text.strip().encode('utf-8'));return request

def ai_result(request_path,image_path,review_path,out_file):
    request=read(request_path);review=read(review_path);image=Path(image_path)
    if request.get('schema')!='interior.ai-request/1':raise ValueError('Invalid AI request')
    if file_sha(request['source']['path'])!=request['source']['sha256']:raise ValueError('Input changed after AI request was prepared')
    if file_sha(image)==request['source']['sha256']:raise ValueError('输出与输入是同一文件内容，不能登记为 AI 已生成')
    for key in request['requiredReview']:
        if review.get(key) not in ['pass','fail']:raise ValueError('Review missing pass/fail field: '+key)
    from PIL import Image
    with Image.open(image) as im:
        output_frame={'width':im.width,'height':im.height,'aspectRatio':im.width/im.height};im.verify()
    artifact={'schema':'interior.ai-result/1','sourceType':'ai-generated','sceneKey':request['sceneKey'],'shotId':request['shotId'],'status':'accepted' if all(review[k]=='pass' for k in request['requiredReview']) else 'delivered-with-observations','requestDigest':digest(request),'image':str(image.resolve()),'sha256':file_sha(image),'review':review,'providerRequestId':review.get('providerRequestId'),'note':'结果由外部图像工具生成；此命令只核对文件与登记真实人工/视觉复核。'}
    artifact.update(seriesKey=request.get('seriesKey'),consistencyGroup=request.get('consistencyGroup'),consistencyReferences=request.get('consistencyReferences',[]),recordedAt=now())
    artifact.update(referencePolicy=request.get('referencePolicy'),sourceFrame=request.get('sourceFrame'),outputFrame=output_frame)
    if request.get('sourceFrame'):
        source=request['sourceFrame'];artifact['frameObservation']={'sameAspectRatio':source['width']*output_frame['height']==source['height']*output_frame['width'],'note':'画幅差异仅记录提示；不拉伸输出、不自动修图，也不以比例相同代替结构与机位识图。'}
    write(out_file,artifact);return artifact
