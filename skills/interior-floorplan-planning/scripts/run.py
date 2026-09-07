"""JSON-only planning handoff; anchors are constructed from a real host wall."""
import argparse,json,math,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'interior-html-modeling/scripts/engine/python'))
from bootstrap import ensure_runtime
ensure_runtime()
from timing import command
with command('interior-floorplan-planning'):
 from common import read,write,digest
 from validate import validate_layout

 def main():
  p=argparse.ArgumentParser();p.add_argument('command',choices=['handoff','observe','anchor']);p.add_argument('layout');p.add_argument('--out',required=True);p.add_argument('--requirements');p.add_argument('--id');p.add_argument('--wall-id');p.add_argument('--offset',type=float,default=0);p.add_argument('--gap',type=float,default=0);a=p.parse_args();d=read(a.layout)
  requirements=None;requirements_out=None
  if a.command!='observe':
   source=Path(a.requirements) if a.requirements else Path(a.layout).with_suffix('.requirements.json')
   target=Path(a.out).with_suffix('.requirements.json')
   if a.requirements or source.exists():
    requirements=read(source)
    if not isinstance(requirements,dict) or requirements.get('schema')!='interior.requirements/1' or requirements.get('projectId')!=d.get('id'):raise ValueError('Requirements schema/projectId differs from this layout')
    if not isinstance(requirements.get('items'),list) or not isinstance(requirements.get('revision'),int) or isinstance(requirements['revision'],bool):raise ValueError('Requirements need items array and integer revision')
    seen=set()
    for item in requirements['items']:
     if not isinstance(item,dict) or not isinstance(item.get('id'),str) or not item['id'] or item['id'] in seen or item.get('status') not in ['confirmed','tentative','unknown','delegated'] or not all(k in item for k in ['topic','value','source']):raise ValueError('Requirements items need unique id, topic, value, source and explicit status')
     seen.add(item['id'])
    requirements_out=str(target)
   elif target.exists():raise ValueError('Output has a previous requirements sidecar; provide the matching brief or choose a new output')
  if a.command=='anchor':
   from shapely.geometry import Polygon,Point
   obj=next(x for x in d['placements'] if x['id']==a.id);w=next(x for x in d['walls'] if x['id']==a.wall_id);room=next(x for x in d['rooms'] if x['id']==obj['roomId'])
   dx,dz=w['b'][0]-w['a'][0],w['b'][1]-w['a'][1];length=math.hypot(dx,dz)
   if not length or not all(math.isfinite(v) for v in [a.offset,a.gap]) or a.offset<0 or a.gap<0 or a.offset+obj['size'][0]>length:raise ValueError('Host wall interval cannot contain this furniture; correct the source interval or selection')
   tx,tz=dx/length,dz/length;nx,nz=-tz,tx;poly=Polygon(room['polygon']);c=poly.representative_point()
   if nx*(c.x-w['a'][0])+nz*(c.y-w['a'][1])<0:nx,nz=-nx,-nz
   distance=w['thickness']/2+obj['size'][2]/2+a.gap
   position=[w['a'][0]+tx*(a.offset+obj['size'][0]/2)+nx*distance,obj['position'][1],w['a'][1]+tz*(a.offset+obj['size'][0]/2)+nz*distance]
   if not poly.covers(Point(position[0],position[2])):raise ValueError('Wall/room association inconsistent; no anchor generated')
   obj.update(position=position,rotationY=math.degrees(math.atan2(nx,nz)))
   d['revision']+=1
  report=validate_layout(d,strict=a.command!='observe')
  if a.command=='observe':write(a.out,report)
  else:
   write(a.out,d);write(str(Path(a.out).with_suffix('.observations.json')),report)
   if requirements is not None:write(requirements_out,requirements)
  print(json.dumps({'ok':True,'output':a.out,'requirementsPath':requirements_out,'requirementsDigest':digest(requirements) if requirements is not None else None,'technicalErrors':len(report['technicalErrors']),'designObservations':len(report['errors'])+len(report['warnings'])},ensure_ascii=False))
 if __name__=='__main__':main()
