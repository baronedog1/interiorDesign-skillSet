"""Host-native image-generation handoff. Does not impersonate or bill an image service."""
from pathlib import Path
from common import read,write,digest,file_sha
from timing import traced,now

def start(job_path,out):
    job=read(job_path)
    if job.get('status')!='ready-for-host-call':raise ValueError('Native tool is unavailable')
    references(read(job['requestPath']))
    for ref in job['referenceImages']:
        if file_sha(ref['path'])!=ref['sha256']:raise ValueError('Prepared attachment changed')
    if Path(out).exists():raise ValueError('Use a new invocation record per attempt')
    actual={'source':'host-native-tool','status':'started-not-generated','toolName':job['tool'],'jobDigest':digest(job),'promptDigest':digest(job['prompt']),'referenceImages':job['referenceImages'],'startedAt':now(),'finishedAt':None,'elapsedMs':None,'outputSha256':None,'providerRequestId':None}
    write(out,actual);return actual

def complete(invocation_path,image_path,out):
    from datetime import datetime
    actual=read(invocation_path)
    if actual.get('status')!='started-not-generated':raise ValueError('Invocation already completed or never started')
    actual.update(finishedAt=now(),status='succeeded',outputSha256=file_sha(image_path))
    actual['elapsedMs']=round((datetime.fromisoformat(actual['finishedAt'])-datetime.fromisoformat(actual['startedAt'])).total_seconds()*1000,3)
    actual['timingScope']='host-call-plus-return-registration; not provider-only latency'
    write(out,actual);return actual

def references(request):
    # Series identity retains every product binding; a frame only receives its
    # projected products, otherwise off-screen reference photos invite relocation.
    products=request.get('frameProductReferences',request.get('productReferences',[]))
    refs=[request['source'],*request.get('consistencyReferences',[]),*products,*request.get('styleReferences',[]),*request.get('layoutReferences',[])]
    attached={}
    for ref in refs:
        if file_sha(ref['path'])!=ref['sha256']:raise ValueError('Attached reference changed: regenerate the request')
        # A dining-set photo can bind several placements without attaching the
        # same bytes five times. Keep semantic roles distinct and every binding.
        key=(ref['role'],ref['sha256'])
        if key not in attached:attached[key]=dict(ref)
        if ref.get('placementId'):
            ids=attached[key].setdefault('placementIds',[])
            if ref['placementId'] not in ids:ids.append(ref['placementId'])
    return list(attached.values())

def compact_references(refs,out,limit):
    """Fit the actual host attachment budget without discarding product originals."""
    if len(refs)<=limit:return refs
    from PIL import Image,ImageOps,ImageDraw,ImageFont
    import math
    result=list(refs)
    for role in ['furniture-identity-reference','style-design-reference-not-layout']:
        group=[r for r in result if r['role']==role]
        if len(result)<=limit:break
        if len(group)<2:continue
        columns=math.ceil(math.sqrt(len(group)));rows=math.ceil(len(group)/columns);cell=max(256,min(1000,4000//max(columns,rows)))
        atlas=Image.new('RGB',(columns*cell,rows*cell),'white');draw=ImageDraw.Draw(atlas);panels=[]
        try:font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',28)
        except OSError:font=ImageFont.load_default()
        for i,ref in enumerate(group):
            with Image.open(ref['path'])as image:
                image=ImageOps.exif_transpose(image).convert('RGBA');image.thumbnail((cell-24,cell-70),Image.Resampling.LANCZOS)
                x=(i%columns)*cell+(cell-image.width)//2;y=(i//columns)*cell+45+(cell-70-image.height)//2;atlas.paste(image,(x,y),image)
            label='P'+str(i+1);draw.text(((i%columns)*cell+12,(i//columns)*cell+8),label,fill='black',font=font)
            panels.append({'panel':label,'originalPath':ref['path'],'originalSha256':ref['sha256'],'placementIds':ref.get('placementIds',[]),'role':role})
        folder=Path(out).with_suffix('');folder.mkdir(parents=True,exist_ok=True);path=folder/(role+'.png');atlas.save(path)
        packed={'path':str(path.resolve()),'sha256':file_sha(path),'role':role,'panels':panels,'placementIds':list(dict.fromkeys(id for r in group for id in r.get('placementIds',[])))}
        first=result.index(group[0]);result=[r for r in result if r not in group];result.insert(first,packed)
    if len(result)>limit:raise ValueError('Attachment roles exceed host capacity; keep the complete request and report capability mismatch')
    return result

@traced('render.prepare-native-call')
def prepare(request_path,capabilities_path,out):
    request=read(request_path);cap=read(capabilities_path)
    if request.get('schema')!='interior.ai-request/1':raise ValueError('Expected prepared same-scene AI request')
    if file_sha(request['source']['path'])!=request['source']['sha256']:raise ValueError('Reference image changed')
    available=cap.get('nativeImage',{})
    ready=available.get('available') is True and bool(available.get('toolName'))
    original=references(request);limit=available.get('maxReferenceImages',5);refs=compact_references(original,out,limit)
    prompt=request['prompt']
    if refs!=original:
        prompt=prompt.split('实际附图顺序与职责（图片编号从1起）：')[0]
        prompt+='\n为适配宿主附图数量，同职责原图按比例白底排成参考板。P编号对应下列产品槽位；每格独立产品原图，不把整张参考板或其排版搬进房间，不改变款式。客户交付仍保留各张原图。\n实际附图顺序与职责（图片编号从1起）：\n'
        import json
        prompt+=json.dumps([{'imageIndex':i+1,'role':r['role'],'placementIds':r.get('placementIds',[]),'panels':[{k:p[k]for k in ['panel','placementIds','role']}for p in r.get('panels',[])]}for i,r in enumerate(refs)],ensure_ascii=False)
    result={'schema':'interior.native-image-job/1','status':'ready-for-host-call' if ready else 'tool-unavailable','requestDigest':digest(request),'requestPath':str(Path(request_path).resolve()),'tool':available.get('toolName') if ready else None,'modelLabel':available.get('modelLabel'),'referenceImages':refs,'referenceImageLimit':limit,'originalReferenceCount':len(original),'prompt':prompt,'sceneKey':request['sceneKey'],'shotId':request['shotId'],'cameraDigest':request['cameraDigest'],'actualInvocation':None,'preparedAt':now(),'note':'This prepares a host-native tool call; it is NOT a generated image. Agent must attach the referenced images to the actual native tool.'};write(out,result);return result

@traced('render.register-result')
def finish(job_path,image_path,invocation_path,review_path,out):
    from render import ai_result
    job=read(job_path);actual=read(invocation_path)
    if job.get('schema')!='interior.native-image-job/1' or job.get('status')!='ready-for-host-call':raise ValueError('No executable native-image job')
    if actual.get('source')!='host-native-tool' or actual.get('toolName')!=job['tool'] or actual.get('status')!='succeeded' or actual.get('jobDigest')!=digest(job):raise ValueError('Missing/mismatched actual host invocation receipt')
    if actual.get('outputSha256')!=file_sha(image_path):raise ValueError('Image does not match invocation output')
    if actual.get('promptDigest') and actual['promptDigest']!=digest(job['prompt']):raise ValueError('Actually registered prompt differs from prepared job')
    if actual.get('referenceImages') is not None and actual['referenceImages']!=job['referenceImages']:raise ValueError('Actually registered attachments differ from prepared job')
    request=read(job['requestPath'])
    if digest(request)!=job['requestDigest']:raise ValueError('Prepared request changed after job creation')
    references(request)
    for ref in job['referenceImages']:
        if file_sha(ref['path'])!=ref['sha256']:raise ValueError('Prepared attachment changed')
    result=ai_result(job['requestPath'],image_path,review_path,out);result.update(tool=actual['toolName'],modelLabel=actual.get('modelLabel'),providerRequestId=actual.get('providerRequestId'),invocationDigest=digest(actual),nativeInvocationSource='host-native-tool',provenanceNote='Invocation provenance relies on the host receipt, not local file contents alone.')
    result['timing']={k:actual.get(k) for k in ['startedAt','finishedAt','elapsedMs','timingScope']}
    if any(v is None for v in result['timing'].values()):result['timing']['observation']='Incomplete historical host timing; do not substitute preparation time or file mtime'
    write(out,result)
    if result['status']=='accepted' and request.get('seriesKey'):
        index=Path(request['seriesPath']);registry=read(index) if index.exists() else {}
        registry.setdefault(request['seriesKey'],{'resultPath':str(Path(out).resolve()),'shotId':request['shotId']})
        write(index,registry)
    return result
