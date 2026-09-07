"""Baiende project/library adapter. One binding, bounded allowlist, no generation or public posts.
Credentials exist only in the local process/managed env file; never in HTML/JSON receipts.
"""
from __future__ import annotations
import argparse,base64,hashlib,json,mimetypes,os,re,time,urllib.request,urllib.parse,urllib.error
from pathlib import Path
from common import read,write,file_sha,atomic_bytes

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):raise ValueError('Redirect refused for authenticated platform operation')

class Platform:
    def __init__(self):
        envfile=Path(os.environ.get('IDK_ENV_FILE',Path.home()/'agent-runtime/secrets/baiende-platform.env')).expanduser()
        env=dict(os.environ)
        if envfile.is_file():
            for line in envfile.read_text(encoding='utf-8-sig').splitlines():
                if not line.strip() or line.lstrip().startswith('#') or '=' not in line:continue
                k,v=line.split('=',1);env.setdefault(k.strip(),v.strip().strip('\"\''))
        self.base=env.get('IDK_API_BASE_URL','https://www.baiende.com/api/v1').rstrip('/')
        self.key=env.get('IDK_API_KEY','');self.tool=env.get('IDK_TOOL_NAME','interior-html-modeling');self.timeout=float(env.get('IDK_REQUEST_TIMEOUT_MS','60000'))/1000
        parsed=urllib.parse.urlsplit(self.base)
        local=parsed.hostname in ['localhost','127.0.0.1','::1'] and env.get('IDK_ALLOW_LOCAL_API')=='YES'
        if parsed.path!='/api/v1' or parsed.username or parsed.password or parsed.query or parsed.fragment:raise ValueError('API base must be an origin ending in /api/v1')
        if parsed.scheme!='https' and not local:raise ValueError('HTTPS required; localhost tests need IDK_ALLOW_LOCAL_API=YES')
        if not self.key:raise ValueError('Managed IDK_API_KEY missing; configure device environment, not skill/HTML')
        self.opener=urllib.request.build_opener(NoRedirect())
    def request(self,method,path,body=None,operation=None):
        allowed=(method=='GET' and re.fullmatch(r'/(auth/profile|projects|projects/[^/?]+/assets|library/summary|library/[^/?]+/items)(\?[^#]*)?',path)) or (method=='POST' and re.fullmatch(r'/(projects|projects/[^/?]+/(assets|preview3d))',path))
        if not allowed:raise ValueError('Operation outside approved private project/library routes')
        headers={'X-IDK-API-Key':self.key,'X-IDK-Tool-Name':self.tool,'Accept':'application/json','Content-Type':'application/json; charset=utf-8'}
        if method=='POST':
            if not operation:raise ValueError('Write needs deterministic idempotency operation')
            headers['Idempotency-Key']='idk-v1-'+hashlib.sha256(operation.encode()).hexdigest()
        payload=None if body is None else json.dumps(body,ensure_ascii=False,allow_nan=False).encode()
        # Retry only transient responses; every write retains the exact same key and bytes.
        for attempt in range(3):
            try:
                req=urllib.request.Request(self.base+path,data=payload,headers=headers,method=method)
                with self.opener.open(req,timeout=self.timeout) as response:raw=response.read(32*1024*1024+1)
                if len(raw)>32*1024*1024:raise ValueError('Platform metadata response too large')
                return json.loads(raw)
            except urllib.error.HTTPError as e:
                if e.code in [429,502,503,504] and attempt<2:time.sleep(.2*(attempt+1));continue
                # Never echo server body, credentials or signed URLs.
                raise RuntimeError(f'{method} platform operation returned HTTP {e.code}') from None
    @staticmethod
    def rows(payload,key):
        if isinstance(payload,list):return payload
        return payload.get(key,payload.get('data',{}).get(key,[]))
    def library(self,library=None):
        return self.request('GET','/library/'+urllib.parse.quote(library,safe='')+'/items?scope=all' if library else '/library/summary?scope=all')
    def bind(self,file,project_id=None,project_name=None,create=False):
        self.request('GET','/auth/profile');current=read(file) if Path(file).exists() else None
        if current and current.get('schema')!='baiende.project-binding.v1':raise ValueError('Invalid project binding')
        if current and project_id and current['projectId']!=project_id:raise ValueError('Cannot silently rebind an existing project')
        if current and current.get('apiBaseUrl')!=self.base:raise ValueError('Project binding belongs to another endpoint')
        pid=project_id or (current or {}).get('projectId');projects=self.rows(self.request('GET','/projects'),'projects')
        matches=[p for p in projects if p.get('id')==pid] if pid else [p for p in projects if (p.get('name') or p.get('title'))==project_name]
        if len(matches)>1:raise ValueError('Project name is ambiguous; specify an id')
        if not matches:
            if pid or not create or not project_name:raise ValueError('Project not visible; no implicit project creation')
            result=self.request('POST','/projects',{'name':project_name,'title':project_name,'sourceType':'external_upload','externalTool':self.tool},'project:'+project_name)
            match=result.get('project',result.get('data',{}).get('project',result));pid=match.get('id')
            if not pid:raise ValueError('Create response has no project id')
            # Verify exact visibility; do not invent GET /projects/{id}.
            matches=[p for p in self.rows(self.request('GET','/projects'),'projects') if p.get('id')==pid]
            if len(matches)!=1:raise ValueError('Created project not found on read-back')
        project=matches[0];bound=current or {'schema':'baiende.project-binding.v1','artifacts':{}}
        origin=self.base.rsplit('/api/v1',1)[0];bound.update(projectId=project['id'],projectName=project.get('name') or project.get('title'),projectUrl=origin+'/projects/'+project['id'],apiBaseUrl=self.base)
        write(file,bound);return bound
    def publish(self,path,binding_path,kind,run_id,folder='design'):
        file=Path(path).resolve();mime=mimetypes.guess_type(file.name)[0];html=file.suffix.lower() in ['.html','.htm']
        if html and kind!='preview3d_html':raise ValueError('HTML must use preview3d_html')
        if not html and mime not in ['image/png','image/jpeg','image/webp','video/mp4','video/webm','video/quicktime']:raise ValueError('ZIP/JSON/PDF are not project media')
        b=self.bind(binding_path);pid=urllib.parse.quote(b['projectId'],safe='');key=folder+'/'+file.name;sha=file_sha(file);prior=b['artifacts'].get(key);assets=self.rows(self.request('GET',f'/projects/{pid}/assets'),'assets')
        if prior:
            if prior['sha256']!=sha:raise ValueError('Changed file needs a new versioned name; no silent overwrite')
            if not any(x.get('id')==prior['assetId'] for x in assets):raise ValueError('Previously published asset missing on read-back')
            return {'ok':True,'status':'verified-existing','assetId':prior['assetId'],'sha256':sha,'projectUrl':b['projectUrl']}
        if any(x.get('folderId')==folder and x.get('name')==file.name for x in assets):raise ValueError('Unbound duplicate asset name; reconcile before upload')
        data=file.read_bytes();source={'externalTool':self.tool,'externalRunId':run_id,'assetKind':kind,'origin':'uploaded','sourceType':'external_upload'}
        if html:
            text=data.decode('utf-8');external=re.search(r'<(?:script|link)[^>]+(?:src|href)=[\"\'](?!data:|blob:)',text,re.I)
            if '<html' not in text.lower() or external or re.search(r'(?:src|href)=[\"\'](?:file:|[a-z]:[\\/])',text,re.I):raise ValueError('HTML has nonportable runtime dependencies')
            response=self.request('POST',f'/projects/{pid}/preview3d',{'name':file.name,'title':file.stem,'folderId':folder,'html':text,'externalTool':self.tool,'externalRunId':run_id},'html:'+pid+':'+sha)
            body=response.get('data',response);asset=body.get('preview3d',{}).get('htmlAsset') or body.get('asset',{})
        else:
            response=self.request('POST',f'/projects/{pid}/assets',{'folderId':folder,**source,'materials':[{'folderId':folder,'name':file.name,'mimeType':mime,'base64':base64.b64encode(data).decode(),**source}]},'media:'+pid+':'+key+':'+sha)
            rows=self.rows(response,'assets');asset=rows[0] if rows else {}
        aid=asset.get('id')
        if not aid:raise ValueError('Upload returned no asset id; not completed')
        verified=next((x for x in self.rows(self.request('GET',f'/projects/{pid}/assets'),'assets') if x.get('id')==aid),None)
        if not verified:raise ValueError('Upload absent from project read-back')
        remote_sha=verified.get('sha256') or verified.get('metadata',{}).get('sha256')
        if remote_sha and remote_sha!=sha:raise ValueError('Remote content digest differs')
        b['artifacts'][key]={'assetId':aid,'assetKind':kind,'folderId':folder,'name':file.name,'mimeType':mime,'sha256':sha,'bytes':len(data),'externalTool':self.tool,'externalRunId':run_id};write(binding_path,b)
        return {'ok':True,'status':'published-readback-verified','assetId':aid,'projectId':b['projectId'],'projectUrl':b['projectUrl'],'sha256':sha,'remoteDigestVerified':bool(remote_sha),'note':'If server does not expose SHA256, read-back proves asset identity, not bytewise remote equality.'}
    def download(self,library,item_id,out):
        rows=self.rows(self.library(library),'items');item=next((x for x in rows if x.get('id')==item_id),None)
        if not item:raise ValueError('Requested asset not visible in authorized library')
        url=item.get('sourcePath') or item.get('sourceStoragePath') or item.get('downloadUrl')
        if not url:raise ValueError('Platform item exposes no downloadable URL; no invented route')
        url=urllib.parse.urljoin(self.base+'/',url);u=urllib.parse.urlsplit(url);origin=urllib.parse.urlsplit(self.base)
        same=(u.scheme,u.netloc)==(origin.scheme,origin.netloc)
        if not same and u.scheme!='https':raise ValueError('External asset download must use HTTPS')
        headers={'X-IDK-API-Key':self.key,'X-IDK-Tool-Name':self.tool} if same else {}
        # Redirects disabled, so account key is never forwarded to another host.
        with self.opener.open(urllib.request.Request(url,headers=headers),timeout=self.timeout) as r:blob=r.read(64*1024*1024+1)
        if len(blob)>64*1024*1024:raise ValueError('Asset exceeds 64 MiB download budget')
        sha=hashlib.sha256(blob).hexdigest();expected=item.get('sha256') or item.get('metadata',{}).get('sha256')
        if expected and expected!=sha:raise ValueError('Downloaded asset digest mismatch')
        atomic_bytes(out,blob);receipt={'ok':True,'assetId':item_id,'libraryId':library,'version':item.get('version'),'file':Path(out).name,'sha256':sha,'remoteDigestVerified':bool(expected),'sourceUrlStored':False};write(str(out)+'.receipt.json',receipt);return receipt

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('profile');q=sub.add_parser('library');q.add_argument('--library')
    q=sub.add_parser('bind');q.add_argument('--binding',required=True);q.add_argument('--project-id');q.add_argument('--project-name');q.add_argument('--create',action='store_true')
    q=sub.add_parser('download');q.add_argument('--library',required=True);q.add_argument('--asset-id',required=True);q.add_argument('--out',required=True)
    q=sub.add_parser('publish');q.add_argument('file');q.add_argument('--binding',required=True);q.add_argument('--kind',required=True);q.add_argument('--run-id',required=True);q.add_argument('--folder',default='design');q.add_argument('--receipt',required=True);q.add_argument('--apply',action='store_true')
    a=p.parse_args()
    try:
        if a.command=='publish' and not a.apply:r={'ok':True,'status':'dry-run','file':a.file,'note':'Private project upload requires task authorization then --apply; public posting unsupported.'}
        else:
            api=Platform()
            if a.command=='profile':r={'ok':bool(api.request('GET','/auth/profile'))}
            elif a.command=='library':r=api.library(a.library)
            elif a.command=='bind':r=api.bind(a.binding,a.project_id,a.project_name,a.create)
            elif a.command=='download':r=api.download(a.library,a.asset_id,a.out)
            else:r=api.publish(a.file,a.binding,a.kind,a.run_id,a.folder);write(a.receipt,r)
        print(json.dumps(r,ensure_ascii=False,indent=2));return 0
    except Exception as e:print(json.dumps({'ok':False,'error':str(e)},ensure_ascii=False));return 2
if __name__=='__main__':raise SystemExit(main())
