"""Host-native image-generation handoff. Does not impersonate or bill an image service."""
from pathlib import Path
from common import read,write,digest,file_sha

def prepare(request_path,capabilities_path,out):
    request=read(request_path);cap=read(capabilities_path)
    if request.get('schema')!='interior.ai-request/1':raise ValueError('Expected prepared same-scene AI request')
    if file_sha(request['source']['path'])!=request['source']['sha256']:raise ValueError('Reference image changed')
    available=cap.get('nativeImage',{})
    ready=available.get('available') is True and bool(available.get('toolName'))
    result={'schema':'interior.native-image-job/1','status':'ready-for-host-call' if ready else 'tool-unavailable','requestDigest':digest(request),'requestPath':str(Path(request_path).resolve()),'tool':available.get('toolName') if ready else None,'modelLabel':available.get('modelLabel'),'referenceImages':[request['source'],*request.get('productReferences',[])],'prompt':request['prompt'],'sceneKey':request['sceneKey'],'shotId':request['shotId'],'cameraDigest':request['cameraDigest'],'actualInvocation':None,'note':'This prepares a host-native tool call; it is NOT a generated image. Agent must attach the referenced images to the actual native tool.'};write(out,result);return result

def finish(job_path,image_path,invocation_path,review_path,out):
    from render import ai_result
    job=read(job_path);actual=read(invocation_path)
    if job.get('schema')!='interior.native-image-job/1' or job.get('status')!='ready-for-host-call':raise ValueError('No executable native-image job')
    if actual.get('source')!='host-native-tool' or actual.get('toolName')!=job['tool'] or actual.get('status')!='succeeded' or actual.get('jobDigest')!=digest(job):raise ValueError('Missing/mismatched actual host invocation receipt')
    if actual.get('outputSha256')!=file_sha(image_path):raise ValueError('Image does not match invocation output')
    request=read(job['requestPath'])
    if digest(request)!=job['requestDigest']:raise ValueError('Prepared request changed after job creation')
    result=ai_result(job['requestPath'],image_path,review_path,out);result.update(tool=actual['toolName'],modelLabel=actual.get('modelLabel'),providerRequestId=actual.get('providerRequestId'),invocationDigest=digest(actual),nativeInvocationSource='host-native-tool',provenanceNote='Invocation provenance relies on the host receipt, not local file contents alone.');write(out,result);return result
