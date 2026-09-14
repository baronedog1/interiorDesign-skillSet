#!/usr/bin/env python3
"""Inventory, validate hashes, and atomically package this skill; no external writes."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

SKIP={'.git','node_modules','__pycache__','.runtime','.pytest_cache'}
DERIVED={'SKILL_MANUAL.pdf','manual/skill-manual.md','manual/skill-flowchart.svg'}
FORBIDDEN_SUFFIXES={'.ttf','.otf','.woff','.woff2','.ttc','.pyc','.part','.tmp'}

def sha(p:Path)->str:
 h=hashlib.sha256()
 with p.open('rb') as f:
  for part in iter(lambda:f.read(1024*1024),b''):h.update(part)
 return h.hexdigest()

def files(root:Path)->list[str]:
 out=[]
 def walk(folder:Path):
  for p in sorted(folder.iterdir()):
   if p.name in SKIP or (p.name.startswith('.env') and p.name!='.env.example'):continue
   if p.is_symlink():raise ValueError('不打包符号链接：'+str(p))
   if p.is_dir():walk(p)
   elif p.suffix.lower() in FORBIDDEN_SUFFIXES:raise ValueError('非正式文件或字体文件不进入包：'+str(p))
   else:out.append(p.relative_to(root).as_posix())
 walk(root)
 return sorted(out)

def inventory(root:Path)->dict:
 spec=json.loads((root/'manual/skill-manual.json').read_text(encoding='utf8'))
 names=sorted(set(files(root))|DERIVED|{'MANIFEST.json'})
 purposes=spec.get('fileDescriptions',{})
 if set(purposes)!=set(names):raise ValueError('文件地图与真实文件不符：'+str(sorted(set(purposes)^set(names))))
 result={'name':root.name,'version':spec['version'],'distribution':'ordinary-agent-skill','file_count':len(names),'files':names,
         'sha256':{n:sha(root/n) for n in names if n!='MANIFEST.json' and (root/n).is_file()},
         'hash_note':'MANIFEST.json不自哈希；外层ZIP摘要随交付提供。','specification':'Skill Product Manager 14.1',
         'runtime_installation':'see deployment receipt','external_publication':'see release receipt'}
 (root/'MANIFEST.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 return result

def check(root:Path)->dict:
 m=json.loads((root/'MANIFEST.json').read_text(encoding='utf8'))
 actual=files(root)
 if actual!=sorted(m['files']) or len(actual)!=m['file_count']:raise ValueError('MANIFEST文件清单不符')
 if set(m['sha256'])!=set(actual)-{'MANIFEST.json'}:raise ValueError('文件摘要清单不完整')
 for n,digest in m['sha256'].items():
  if sha(root/n)!=digest:raise ValueError('文件内容摘要不符：'+n)
 return {'ok':True,'version':m['version'],'files':len(actual),'all_payload_hashes_verified':True}

def package(root:Path,out:Path)->dict:
 root=root.resolve();out=out.resolve()
 if out.is_relative_to(root):raise ValueError('ZIP必须输出到Skill目录以外，避免自包含')
 report=check(root);out.parent.mkdir(parents=True,exist_ok=True)
 part=out.with_suffix(out.suffix+'.part')
 try:
  with zipfile.ZipFile(part,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
   for name in files(root):z.write(root/name,root.name+'/'+name)
  with zipfile.ZipFile(part) as z:
   broken=z.testzip()
   if broken:raise ValueError('ZIP CRC错误：'+broken)
   with tempfile.TemporaryDirectory(prefix='title-cover-reopen-') as temp:
    z.extractall(temp)
    check(Path(temp)/root.name)
  os.replace(part,out)
 finally:
  if part.exists():part.unlink()
 report.update({'zip':str(out),'bytes':out.stat().st_size,'sha256':sha(out),'crc':'pass','reextract_hash_check':'pass'})
 return report

def main()->int:
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['inventory','check','zip']);p.add_argument('root',type=Path);p.add_argument('--out',type=Path);a=p.parse_args()
 try:
  if a.command=='inventory':result=inventory(a.root);result={'ok':True,'files':result['file_count'],'version':result['version']}
  elif a.command=='check':result=check(a.root)
  else:
   if not a.out:raise ValueError('zip需要--out')
   result=package(a.root,a.out)
  print(json.dumps(result,ensure_ascii=False,indent=2));return 0
 except (ValueError,OSError,KeyError,zipfile.BadZipFile) as e:
  print(json.dumps({'ok':False,'error':str(e)},ensure_ascii=False),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
