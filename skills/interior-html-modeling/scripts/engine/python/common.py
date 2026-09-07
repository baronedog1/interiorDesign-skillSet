"""Small shared I/O and identity helpers. Never searches arbitrary directories or contacts services."""
from __future__ import annotations
import hashlib,json,os,tempfile
from pathlib import Path
SHARED=Path(__file__).resolve().parents[1]
def read(path):
    with Path(path).open(encoding='utf-8') as f:return json.load(f,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Non-finite JSON number: '+x)))
def canonical(data):return json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
def digest(data):return hashlib.sha256(canonical(data)).hexdigest()
def file_sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def atomic_bytes(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.'+path.name+'.',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
def write(path,data):atomic_bytes(path,json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8')+b'\n')
def resources():return read(SHARED/'catalog/components.json'),read(SHARED/'catalog/styles.json')
def runtime_identity():
    return digest({str(p.relative_to(SHARED)):file_sha(p) for folder in ['runtime','catalog'] for p in sorted((SHARED/folder).rglob('*')) if p.is_file()})
def require_schema(data,name):
    from jsonschema import Draft202012Validator
    issues=sorted(Draft202012Validator(read(SHARED/'schemas'/name)).iter_errors(data),key=lambda e:str(e.path))
    if issues:raise ValueError('; '.join('/'.join(map(str,e.path))+': '+e.message for e in issues[:12]))
