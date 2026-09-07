"""Validate/bundle authorized local native assets. Never scans the whole disk."""
from __future__ import annotations
import base64,hashlib,json,struct,re
from pathlib import Path
from common import read,write,atomic_bytes,SHARED

def parse_glb(data:bytes):
    if len(data)<28:raise ValueError('GLB too small')
    magic,version,size=struct.unpack_from('<III',data)
    if magic!=0x46546c67 or version!=2 or size!=len(data):raise ValueError('Invalid GLB header/length')
    start=12;document=None;binary=None
    while start+8<=len(data):
        length,kind=struct.unpack_from('<II',data,start);start+=8
        if start+length>len(data):raise ValueError('GLB truncated chunk')
        if kind==0x4e4f534a:document=json.loads(data[start:start+length])
        elif kind==0x004e4942:binary=data[start:start+length]
        start+=length
    if start!=len(data) or document is None or binary is None:raise ValueError('Missing GLB JSON/BIN')
    if document.get('asset',{}).get('version')!='2.0':raise ValueError('Expected glTF 2.0')
    if len(document.get('buffers',[]))!=1 or document['buffers'][0].get('uri'):raise ValueError('GLB must embed one binary buffer')
    if document.get('skins') or document.get('animations'):raise ValueError('Bake animated furniture to static mesh before import')
    if set(document.get('extensionsRequired',[]))-{'KHR_texture_transform','KHR_materials_emissive_strength'}:raise ValueError('Unsupported required compression/material extension; preconvert offline')
    for image in document.get('images',[]):
        if image.get('uri') and not re.match(r'^data:image/(png|jpeg|webp);base64,',image['uri']):raise ValueError('External GLB image forbidden')
    for mesh in document.get('meshes',[]):
        for p in mesh.get('primitives',[]):
            if p.get('mode',4)!=4 or p.get('targets') or p.get('extensions',{}).get('KHR_draco_mesh_compression'):raise ValueError('Use uncompressed static triangles')
    return document

def validate_assets(layout):
    assets={}
    for a in layout.get('nativeAssets',[]):
        if a['id'] in assets:raise ValueError('Duplicate nativeAsset id')
        data=base64.b64decode(a['modelBase64'],validate=True)
        if len(data)>64*1024*1024:raise ValueError('Native asset exceeds supported 64MiB per asset')
        parse_glb(data)
        if a.get('sha256') and hashlib.sha256(data).hexdigest()!=a['sha256']:raise ValueError('Native asset digest mismatch')
        assets[a['id']]=a
    for p in layout.get('placements',[]):
        if not p.get('nativeAssetId'):continue
        a=assets.get(p['nativeAssetId'])
        if not a:raise ValueError('Missing native asset '+p['nativeAssetId'])
        if a['componentId']!=p['componentId']:raise ValueError('Native asset category does not match placement')
        ratios=[v/d for v,d in zip(p['size'],a['size'])]
        if a.get('deform','uniform')=='uniform' and max(ratios)-min(ratios)>.002:raise ValueError('Native asset only supports uniform scaling')
    return {'ok':True,'nativeAssets':len(assets)}

def bundle_library(index_path,out):
    path=Path(index_path).resolve();index=read(path)
    if index.get('schema')!='interior.asset-library/1':raise ValueError('Expected interior.asset-library/1')
    assets=[]
    for meta in index['items']:
        target=(path.parent/meta['modelPath']).resolve()
        if not target.is_relative_to(path.parent) or not target.is_file():raise ValueError('Asset path is missing or outside authorized directory')
        blob=target.read_bytes();parse_glb(blob)
        if meta.get('sha256') and meta['sha256']!=hashlib.sha256(blob).hexdigest():raise ValueError('Asset library hash does not match file')
        a={k:v for k,v in meta.items() if k not in ['modelPath','thumbnail']};a.update(modelBase64=base64.b64encode(blob).decode(),sha256=hashlib.sha256(blob).hexdigest());assets.append(a)
    result={'schema':'interior.asset-bundle/1','assets':assets};write(out,result);return {'ok':True,'assets':len(assets),'output':str(out)}

def import_html(path,out):
    from html.parser import HTMLParser
    class Extract(HTMLParser):
        def __init__(self):super().__init__();self.inside=None;self.data={}
        def handle_starttag(self,tag,attrs):
            a=dict(attrs)
            if tag=='script' and a.get('type')=='application/json' and a.get('id') in ['saved-project','project-json']:self.inside=a['id'];self.data[self.inside]=''
        def handle_endtag(self,tag):
            if tag=='script':self.inside=None
        def handle_data(self,text):
            if self.inside:self.data[self.inside]+=text
    parser=Extract();parser.feed(Path(path).read_text(encoding='utf-8'))
    saved=json.loads(parser.data['saved-project']) if parser.data.get('saved-project') else None
    layout=saved['layout'] if saved else json.loads(parser.data['project-json'])
    if saved:layout['customStyle']=saved['styleRecipe']
    from validate import validate_layout
    validate_layout(layout,strict=True);write(out,layout)
    state_path=Path(out).with_suffix('.editor.json')
    if saved:write(state_path,saved)
    return {'ok':True,'layout':str(out),'editorState':str(state_path) if saved else None,'source':'returned-html-json-only','executedUntrustedScripts':False}

def audit_placement(path,placement):
    import subprocess,shutil
    node=shutil.which('node')
    if not node:raise RuntimeError('摆放同核检查需要Node.js；HTML内核无需额外安装')
    script='const fs=require("fs"),S=require(process.argv[1]),p=JSON.parse(fs.readFileSync(0,"utf8"));console.log(JSON.stringify(S.audit(p,process.argv[2])));'
    p=subprocess.run([node,'-e',script,str(SHARED/'runtime/spatial.js'),placement],input=Path(path).read_text(encoding='utf-8-sig'),text=True,capture_output=True,timeout=30,check=True)
    return json.loads(p.stdout)
