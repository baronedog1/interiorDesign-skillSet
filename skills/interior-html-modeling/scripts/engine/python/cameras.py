"""One bounded camera planner: keep presets, sample inside the room, add wall-normal fronts.
No geometry/light edits; openings, open doors, curtains and tall furniture are occluders.
Geometry-ready is not visual acceptance. All methods are shared, never per-project patches.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
import numpy as np
from shapely.geometry import Point, Polygon, LineString
from common import require_schema
from timing import traced


def vec(x): return np.asarray(x, dtype=float)


def corners(p):
    a=math.radians(p['rotationY']); c,s=math.cos(a),math.sin(a)
    x,y,z=p['position']; w,h,d=p['size']
    return [[x+c*u+s*v,y+yy,z-s*u+c*v] for u in [-w/2,w/2] for yy in [0,h] for v in [-d/2,d/2]]


def basis(position,target,up=(0,1,0)):
    f=vec(target)-vec(position); f/=max(np.linalg.norm(f),1e-9)
    r=np.cross(f,vec(up)); r/=max(np.linalg.norm(r),1e-9)
    return f,r,np.cross(r,f)


def projected(shot,points):
    if not len(points): return {'complete':True,'minDepth':None,'maxAbsNDC':0.0}
    f,r,u=basis(shot['position'],shot['target'],shot['up'])
    delta=vec(points)-vec(shot['position']); depth=delta@f
    if depth.min()<=.04: return {'complete':False,'minDepth':float(depth.min()),'maxAbsNDC':1e9}
    t=math.tan(math.radians(shot['fov'])/2); aspect=shot['frame']['width']/shot['frame']['height']
    ndc=np.column_stack(((delta@r)/(depth*t*aspect),(delta@u)/(depth*t)))
    return {'complete':bool(np.abs(ndc).max()<=.965),'minDepth':float(depth.min()),'maxAbsNDC':float(np.abs(ndc).max()),'ndcBounds':[ndc.min(axis=0).tolist(),ndc.max(axis=0).tolist()]}


def base_shot(id,name,room,position,target,fov,frame,kind='preset'):
    return {'id':id,'name':name,'roomId':room,'kind':kind,'position':list(map(float,position)),
            'target':list(map(float,target)),'up':[0,1,0],'fov':float(fov),'projection':'perspective',
            'frame':dict(frame),'subjectIds':[],'status':'ready','reviewNotes':[],'metrics':{},
            'visibility':{'walls':True,'ceiling':True,'doorsOpen':True,'cutaway':False}}


class Occluders:
    """Oriented solid boxes. Vectorised slab queries keep the candidate search bounded."""
    def __init__(self,layout):
        records=[]
        def box(id,position,size,rotation=0):
            if min(size)<=.002:return
            a=math.radians(rotation);c,s=math.cos(a),math.sin(a)
            axes=vec([[c,0,-s],[0,1,0],[s,0,c]])
            records.append((id,vec(position)+vec([0,size[1]/2,0]),axes,vec(size)/2))
        for p in layout['placements']:
            if p['size'][1]>.08:box(p['id'],p['position'],p['size'],p['rotationY'])
        for w in layout['walls']:
            a,b=vec(w['a']),vec(w['b']); length=float(np.linalg.norm(b-a)); tangent=(b-a)/length
            yaw=-math.degrees(math.atan2(tangent[1],tangent[0])); height=w['height']
            def solid(lo,hi,bottom,top):
                pos=a+tangent*(lo+hi)/2
                box(w['id'],[pos[0],bottom,pos[1]],[hi-lo,top-bottom,w['thickness']],yaw)
            previous=0
            for o in sorted((x for x in layout['openings'] if x['wallId']==w['id']),key=lambda x:x['offset']):
                lo=o['offset'];hi=lo+o['width'];solid(previous,lo,0,height)
                solid(lo,hi,0,o['sill']);solid(lo,hi,o['sill']+o['height'],height)
                if o['type']=='door':
                    # Same hinge/1.3-radian open pose as architecture-kit.js.
                    hinge=a+tangent*lo; angle=yaw+math.degrees(1.3);ra=math.radians(angle)
                    centre=hinge+vec([math.cos(ra),-math.sin(ra)])*o['width']/2
                    box(o['id'],[centre[0],o['sill'],centre[1]],[max(.04,o['width']-.035),o['height'],.06],angle)
                previous=hi
            solid(previous,length,0,height)
        self.ids=np.array([x[0] for x in records],dtype=object)
        self.centres=vec([x[1] for x in records]);self.axes=vec([x[2] for x in records]);self.halves=vec([x[3] for x in records])

    def standing(self,position):
        if not len(self.ids):return True
        local=np.einsum('bij,bj->bi',self.axes,vec(position)-self.centres)
        return not bool(np.any(np.all(np.abs(local)<self.halves+.08,axis=1)))

    def rays(self,position,directions,ignore=()):
        ds=vec(directions)
        if not len(self.ids):return np.full(len(ds),np.inf)
        origin=np.einsum('bij,bj->bi',self.axes,vec(position)-self.centres)
        direction=np.einsum('bij,rj->rbi',self.axes,ds)
        parallel=np.abs(direction)<1e-10
        safe=np.where(parallel,1.,direction)
        a=(-self.halves-origin)/safe;b=(self.halves-origin)/safe
        low=np.where(parallel,-np.inf,np.minimum(a,b));high=np.where(parallel,np.inf,np.maximum(a,b))
        entry=low.max(axis=2);exit=high.min(axis=2)
        invalid_parallel=np.any(parallel&(np.abs(origin)>self.halves),axis=2)
        hit=(~invalid_parallel)&(exit>=np.maximum(entry,.04))
        if ignore:hit[:,np.isin(self.ids,list(ignore))]=False
        return np.where(hit,np.maximum(entry,.04),np.inf).min(axis=1)

    def clear_ratio(self,position,subjects):
        samples=[]
        for p in subjects:
            c=vec(corners(p));mid=c.mean(axis=0)
            # Slight inset avoids treating contact at subject borders as total obstruction.
            samples.extend([mid,*(mid+(c-mid)*.78)])
        if not samples:return 1.
        delta=vec(samples)-vec(position);length=np.linalg.norm(delta,axis=1)
        rays=delta/np.maximum(length[:,None],1e-9)
        distances=self.rays(position,rays,[p['id'] for p in subjects])
        return float(np.mean(distances>=length-.04))

    def foreground_ratio(self,shot,subject_distance):
        f,r,u=basis(shot['position'],shot['target']);t=math.tan(math.radians(shot['fov'])/2)
        aspect=shot['frame']['width']/shot['frame']['height']
        ds=vec([f+r*x*t*aspect+u*y*t for x in np.linspace(-.8,.8,5) for y in [-.65,0,.65]])
        ds/=np.linalg.norm(ds,axis=1)[:,None]
        distance=self.rays(shot['position'],ds,shot['subjectIds'])
        return float(np.mean(distance<min(2.2,subject_distance*.80)))


def _subjects(layout,room):
    ps={p['id']:p for p in layout['placements']}
    explicit=[ps[x] for x in room['subjectIds'] if x in ps and ps[x]['roomId']==room['id']]
    if explicit:return explicit
    # Only infer missing subjects inside this room. Never borrow furniture from
    # an adjacent living/dining zone because it happens to be close to the camera.
    name=(room.get('type') or room['name']).casefold()
    roles=next((roles for names,roles in [
      (['卧','bedroom'],['bed.','table.side']),
      (['餐','dining'],['table.dining','chair.dining']),
      (['客','living'],['sofa.','table.coffee','tv.console']),
      (['厨','kitchen'],['kitchen','cabinet']),
      (['卫','bath'],['vanity','toilet','shower']),
      (['书','study'],['desk','chair']),
      (['阳台','balcony'],['chair','plant'])] if any(k in name for k in names)),[])
    candidates=[p for p in ps.values() if p['roomId']==room['id']]
    selected=[p for p in candidates if any(k in p['componentId'] for k in roles)]
    return selected or candidates


def _points(subjects,height,detail=False):
    points=[v for p in subjects for v in corners(p)]
    if not points:return [],None
    a=vec(points);center=(a.min(axis=0)+a.max(axis=0))/2
    if not detail:points.extend([[center[0],.025,center[2]],[center[0],height-.025,center[2]]])
    return points,center


def _evaluate(layout,room,position,target,subjects,frame,kind,occluders,detail=False):
    points,center=_points(subjects,layout['floor']['height'],detail)
    f,r,u=basis(position,target);delta=vec(points)-vec(position);depth=delta@f
    if depth.min()<=.06:return None
    aspect=frame['width']/frame['height'];need=max(float(np.abs(delta@r/depth).max()/aspect),float(np.abs(delta@u/depth).max()))/.94
    required=max(38. if kind=='front' else 44.,math.degrees(2*math.atan(need)))
    shot=base_shot(room['id']+('-front' if kind=='front' else ''),room['name']+(' · 正视' if kind=='front' else ' · 局部' if detail else ''),room['id'],position,target,min(90.,required),frame,'detail' if detail else kind)
    shot['subjectIds']=[p['id'] for p in subjects]
    clear=occluders.clear_ratio(position,subjects);foreground=occluders.foreground_ratio(shot,float(np.linalg.norm(center-vec(position))))
    shot['metrics']={**projected(shot,points),'requiredFov':round(required,3),'insideRoom':True,'cameraHeight':float(position[1]),'ceilingAndFloorAnchors':not detail,'purpose':'detail' if detail else 'room','clearSampleRatio':round(clear,3),'foregroundCoverRatio':round(foreground,3)}
    if not shot['metrics']['complete'] or clear<.55 or foreground>.35:
        shot['status']='review';shot['reviewNotes']=['完整包络、遮挡抽样或近景占幅存在风险；保留候选，实际截图复核。不隐藏实体。']
    else:shot['reviewNotes']=['几何检查可用；实际截图仍需逐图视觉复核。']
    penalty=max(0,required-90)*50+(1-clear)*160+foreground*140+required+abs(float(position[1])-1.4)*3
    return penalty,shot


def _preview(layout,room,frame,occluders,subjects=None,detail=False):
    subjects=_subjects(layout,room) if subjects is None else subjects
    points,centre=_points(subjects,layout['floor']['height'],detail)
    if centre is None:return None
    poly=Polygon(room['polygon']).buffer(-.14);x0,z0,x1,z1=Polygon(room['polygon']).bounds
    choices=[];count=0
    for x in np.linspace(x0+.18,x1-.18,7):
        for z in np.linspace(z0+.18,z1-.18,7):
            if not poly.covers(Point(float(x),float(z))):continue
            distance=math.hypot(x-centre[0],z-centre[2])
            if distance<.45:continue
            for h in [1.4,1.25,1.55]:
                position=[x,h,z]
                if not occluders.standing(position):continue
                count+=1
                # The 12-degree preview rule applies to full-room, not explicit detail shots.
                pitch=math.atan2((centre[1] if detail else layout['floor']['height']/2)-h,distance)
                if not detail:pitch=float(np.clip(pitch,-math.radians(12),math.radians(12)))
                target=[centre[0],h+math.tan(pitch)*distance,centre[2]]
                s=_evaluate(layout,room,position,target,subjects,frame,'preset',occluders,detail)
                if s:choices.append(s)
    if not choices:return None
    shot=min(choices,key=lambda x:x[0])[1];shot['metrics']['candidateCount']=count
    return shot


def _room_preview(layout,room,frame,occluders):
    # A detail is not a substitute for the whole-space reference.
    return _preview(layout,room,frame,occluders)


def generic_presets(layout):
    floor=Polygon(layout['floor']['outline']);x0,z0,x1,z1=floor.bounds;cx,cz=(x0+x1)/2,(z0+z1)/2;size=max(x1-x0,z1-z0)
    presets={'overview':{'title':'全屋鸟瞰','pos':[cx+size*.97,size*1.2,cz+size*1.2],'target':[cx,.4,cz],'fov':40},'plan':{'title':'正交平面','pos':[cx,size*2,cz+.001],'target':[cx,0,cz],'fov':38}}
    obstacles=Occluders(layout);frame={'width':1280,'height':960}
    for room in layout['rooms']:
        shot=_room_preview(layout,room,frame,obstacles)
        if shot:
            presets[room['id']]={'title':shot['name'],'pos':shot['position'],'target':shot['target'],'fov':shot['fov'],'subjectIds':shot['subjectIds'],'previewMetrics':shot['metrics']}
        else:
            p=Polygon(room['polygon']).representative_point();presets[room['id']]={'title':room['name']+' · 待调整','pos':[p.x,1.4,p.y],'target':[p.x,1.4,p.y-.6],'fov':75,'subjectIds':room['subjectIds'],'previewStatus':'review'}
    return presets


def front_view(layout,room,frame,max_fov=90,occluders=None,subjects=None,label='front'):
    subjects=_subjects(layout,room) if subjects is None else subjects
    occluders=occluders or Occluders(layout);poly=Polygon(room['polygon']);safe=poly.buffer(-.14)
    empty=not subjects
    if empty:
        c=poly.representative_point()
        subjects=[dict(id='__architecture__',position=[c.x,0,c.y],size=[.1,layout['floor']['height'],.1],rotationY=0)]
    _,center=_points(subjects,layout['floor']['height'])
    adjacent=[w for w in layout['walls'] if LineString([w['a'],w['b']]).distance(poly.boundary)<=w['thickness']/2+.16]
    wall=next((w for w in adjacent if w['id']==room.get('frontWallId')),None)
    if wall is None:
        yaw=math.radians(subjects[0]['rotationY']);front=vec([math.sin(yaw),math.cos(yaw)])
        options=[]
        for w in adjacent:
            tangent=vec(w['b'])-vec(w['a']);tangent/=np.linalg.norm(tangent);normal=vec([-tangent[1],tangent[0]])
            if abs(float(normal@front))>.99:options.append((LineString([w['a'],w['b']]).distance(Point(float(center[0]),float(center[2]))),w))
        if options:wall=min(options,key=lambda x:x[0])[1]
    choices=[]
    if wall:
        tangent=vec(wall['b'])-vec(wall['a']);tangent/=np.linalg.norm(tangent);normal=vec([-tangent[1],tangent[0]])
        p=poly.representative_point()
        if (vec([p.x,p.y])-vec(wall['a']))@normal<0:normal=-normal
    else:
        yaw=math.radians(subjects[0]['rotationY']);normal=vec([math.sin(yaw),math.cos(yaw)]);tangent=vec([normal[1],-normal[0]])
    if not empty and any(k in subjects[0].get('componentId','') for k in ['sofa.','bed.','tv.','vanity','cabinet','kitchen','washer','bench.']):
        # Furniture front is local +Z; never choose the reverse wall merely because it is closer.
        yaw=math.radians(subjects[0]['rotationY']);front=vec([math.sin(yaw),math.cos(yaw)])
        if not room.get('frontWallId') or abs(float(normal@front))>.99:normal=front;tangent=vec([normal[1],-normal[0]])
    if empty:
        # Only an empty architectural view uses the long axis; fixtures retain their true front.
        edges=[vec(b)-vec(a) for a,b in zip(room['polygon'],room['polygon'][1:]+room['polygon'][:1])]
        longest=max(edges,key=lambda e:np.linalg.norm(e));normal=longest/np.linalg.norm(longest);tangent=vec([normal[1],-normal[0]])
    for direction in ([1,-1] if empty else [1]):
        distance=math.hypot(poly.bounds[2]-poly.bounds[0],poly.bounds[3]-poly.bounds[1])+.5
        for offset in [0,-.18,.18]:
            aim=center[[0,2]]+tangent*offset
            for d in np.linspace(distance,.5,35):
                xz=aim+normal*d*direction
                if not safe.covers(Point(*xz)):continue
                for h in [1.4,1.25,1.55]:
                    pos=[xz[0],h,xz[1]]
                    if not occluders.standing(pos):continue
                    result=_evaluate(layout,room,pos,[aim[0],h,aim[1]],subjects,frame,'front',occluders)
                    if result:
                        score,shot=result
                        actual=vec(shot['position'])[[0,2]]-vec(shot['target'])[[0,2]];actual/=np.linalg.norm(actual)
                        angle=math.degrees(math.acos(float(np.clip(actual@(normal*direction),-1,1))))
                        shot['metrics'].update({'frontAxis':list(map(float,normal*direction)),'referenceWallId':wall['id'] if wall else None,'horizontal':True,'frontAngleDegrees':round(angle,6)});choices.append((score+abs(offset)*5,shot))
    if not choices:
        p=poly.representative_point();target=[center[0],1.4,center[2]];pos=[p.x,1.4,p.y]
        if math.dist(pos,target)<.05:target[2]-=.5
        shot=base_shot(room['id']+'-front',room['name']+' · 正视待调整',room['id'],pos,target,80,frame,'front')
        shot['id']=room['id']+'-'+label;shot['status']='review';shot['subjectIds']=[] if empty else [p['id'] for p in subjects];shot['metrics']['frontSolved']=False;shot['reviewNotes']=['正视站位尚无可用解；这是诊断图，不是假称正视合格。回查主体/宿主墙/房间输入，不隐藏实体。'];return shot
    shot=min(choices,key=lambda x:x[0])[1];shot['metrics']['candidateCount']=len(choices)
    shot['id']=room['id']+'-'+label;shot['name']=room['name']+' · '+label+' 正视';shot['metrics']['frontSolved']=True
    if empty:shot['subjectIds']=[];shot['metrics']['architecturalSubject']=True
    if shot['fov']>max_fov:shot['fov']=max_fov;shot['status']='review'
    return shot


def validate_plan(plan,scene=None):
    require_schema(plan,'cameras.schema.json')
    if len({s['id'] for s in plan['shots']})!=len(plan['shots']):raise ValueError('相机 ID 重复')
    if scene and (plan['sceneKey']!=scene['sceneKey'] or plan['layoutHash']!=scene['layoutHash']):raise ValueError('相机对应的场景版本已过期')
    subjects={p['id'] for p in scene['layout']['placements']} if scene else None
    rooms={r['id'] for r in scene['layout']['rooms']} if scene else None
    for shot in plan['shots']:
        direction=vec(shot['target'])-vec(shot['position']);up=vec(shot['up'])
        if np.linalg.norm(direction)<.05 or np.linalg.norm(np.cross(direction,up))<1e-6:raise ValueError('相机方向或 up 向量退化: '+shot['id'])
        if shot['projection']=='orthographic' and shot.get('orthographicSpan',0)<=0:raise ValueError('正交相机缺少有效 span')
        if subjects is not None and set(shot['subjectIds'])-subjects:raise ValueError('相机主体不存在')
        if rooms is not None and shot['roomId'] is not None and shot['roomId'] not in rooms:raise ValueError('相机房间不存在')
    return plan


@traced('camera.find')
def compile_cameras(scene,frame,add_front=True):
    layout=scene['layout'];rooms={r['id']:r for r in layout['rooms']};ps={p['id']:p for p in layout['placements']};shots=[];obstacles=Occluders(layout)
    for id,p in scene['presets'].items():
        rid=id if id in rooms else ('living' if id=='tv' and 'living' in rooms else None)
        detail=p.get('previewMetrics',{}).get('purpose')=='detail'
        s=base_shot(id,p['title'],rid,p['pos'],p['target'],p['fov'],frame,'overview' if id in ['overview','plan'] else 'detail' if detail else 'preset')
        if id in ['overview','plan']:s['visibility']['ceiling']=False
        if id=='plan':
            s['projection']='orthographic';s['up']=[0,0,-1];b=Polygon(layout['floor']['outline']).bounds;s['orthographicSpan']=max((b[3]-b[1])*1.1,(b[2]-b[0])*frame['height']/frame['width']*1.1)
        if rid:
            s['subjectIds']=list(p.get('subjectIds',rooms[rid]['subjectIds']));subjects=[ps[x] for x in s['subjectIds'] if x in ps];points,center=_points(subjects,layout['floor']['height'],detail)
            s['metrics']={**projected(s,points),'ceilingAndFloorAnchors':not detail,'purpose':'detail' if detail else 'room','clearSampleRatio':round(obstacles.clear_ratio(s['position'],subjects),3)}
            s['metrics']['foregroundCoverRatio']=round(obstacles.foreground_ratio(s,float(np.linalg.norm(center-vec(s['position'])))),3) if center is not None else 0
            if not s['metrics']['complete'] or s['metrics']['clearSampleRatio']<.55 or s['metrics']['foregroundCoverRatio']>.35 or not obstacles.standing(s['position']) or p.get('previewStatus')=='review':s['status']='review'
            s['reviewNotes']=['保留原预设参数；几何/近景占幅已抽检，实际截图仍需复核。']
        shots.append(s)
    if add_front:
        for room in layout['rooms']:
            own=[p for p in layout['placements'] if p['roomId']==room['id']]
            sofas=[p for p in own if p['componentId'].startswith('sofa.')]
            tvs=[p for p in own if p['componentId'].startswith('tv.')]
            groups=[('sofa-front',sofas),('tv-front',tvs)] if sofas else [('front',None)]
            if any(k in (room.get('type','')+' '+room['name']).lower() for k in ['balcony','阳台']):
                fixtures=[p for p in own if any(k in p['componentId'] for k in ['washer','vanity','cabinet','bench.'])]
                if fixtures:groups=[('front',[fixtures[0]])]+[('fixture-'+str(i)+'-front',[p]) for i,p in enumerate(fixtures[1:],1)]
            for label,subjects in groups:
                if subjects==[]:continue
                shot=front_view(layout,room,frame,occluders=obstacles,subjects=subjects,label=label)
                if shot:shots.append(shot)
        # Per-room primary frames precede supplements. Overview/plan are not room photographs.
        room_order={r['id']:i for i,r in enumerate(layout['rooms'])}
        shots.sort(key=lambda s:(room_order.get(s['roomId'],-1),0 if s['kind']=='front' else 1))
    for index,item in enumerate(scene.get('editorState',{}).get('cameras',[])):
        camera=item['camera'];rid=camera.get('view') if camera.get('view') in rooms else None
        s=base_shot('saved-'+str(index+1),item.get('name','用户保存机位'),rid,camera['position'],camera['target'],camera['fov'],frame)
        s['metrics']['source']='user-saved-editor-camera'
        s['subjectIds']=[p['id'] for p in _subjects(layout,rooms[rid])] if rid else []
        if camera.get('type')=='orthographic':
            s['projection']='orthographic';s['up']=[0,0,-1];bounds=Polygon(layout['floor']['outline']).bounds
            s['orthographicSpan']=max(bounds[3]-bounds[1],(bounds[2]-bounds[0])*frame['height']/frame['width'])*1.16/max(camera.get('zoom',1),.01)
        else:s['fov']=math.degrees(2*math.atan(math.tan(math.radians(s['fov'])/2)/max(camera.get('zoom',1),.01)))
        s['visibility'].update(ceiling=bool(camera.get('roof')),cutaway=bool(camera.get('cut')))
        shots.append(s)
    result={'schema':'interior.cameras/1','sceneKey':scene['sceneKey'],'layoutHash':scene['layoutHash'],'shots':shots}
    validate_plan(result,scene);return result
