"""Host-native image-generation handoff. Does not impersonate or bill an image service."""
from pathlib import Path
from common import read,write,digest,file_sha
from timing import traced,now

def start(job_path,out):
    job=read(job_path)
    if job.get('status')!='ready-for-host-call':raise ValueError('Native tool is unavailable')
    references(read(job['requestPath']))
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
    refs=[request['source'],*request.get('consistencyReferences',[]),*request.get('productReferences',[])]
    for ref in refs:
        if file_sha(ref['path'])!=ref['sha256']:raise ValueError('Attached reference changed: regenerate the request')
    return refs

@traced('render.prepare-native-call')
def prepare(request_path,capabilities_path,out):
    request=read(request_path);cap=read(capabilities_path)
    if request.get('schema')!='interior.ai-request/1':raise ValueError('Expected prepared same-scene AI request')
    if file_sha(request['source']['path'])!=request['source']['sha256']:raise ValueError('Reference image changed')
    available=cap.get('nativeImage',{})
    ready=available.get('available') is True and bool(available.get('toolName'))
    result={'schema':'interior.native-image-job/1','status':'ready-for-host-call' if ready else 'tool-unavailable','requestDigest':digest(request),'requestPath':str(Path(request_path).resolve()),'tool':available.get('toolName') if ready else None,'modelLabel':available.get('modelLabel'),'referenceImages':references(request),'prompt':request['prompt'],'sceneKey':request['sceneKey'],'shotId':request['shotId'],'cameraDigest':request['cameraDigest'],'actualInvocation':None,'preparedAt':now(),'note':'This prepares a host-native tool call; it is NOT a generated image. Agent must attach the referenced images to the actual native tool.'};write(out,result);return result

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
    result=ai_result(job['requestPath'],image_path,review_path,out);result.update(tool=actual['toolName'],modelLabel=actual.get('modelLabel'),providerRequestId=actual.get('providerRequestId'),invocationDigest=digest(actual),nativeInvocationSource='host-native-tool',provenanceNote='Invocation provenance relies on the host receipt, not local file contents alone.')
    result['timing']={k:actual.get(k) for k in ['startedAt','finishedAt','elapsedMs','timingScope']}
    if any(v is None for v in result['timing'].values()):result['timing']['observation']='Incomplete historical host timing; do not substitute preparation time or file mtime'
    write(out,result)
    if result['status']=='accepted' and request.get('seriesKey'):
        index=Path(request['seriesPath']);registry=read(index) if index.exists() else {}
        registry.setdefault(request['seriesKey'],{'resultPath':str(Path(out).resolve()),'shotId':request['shotId']})
        write(index,registry)
    return result
