"""One geometric validation pass for the layout. No automatic repair or invented walls."""
from __future__ import annotations
import math
from collections import defaultdict,deque
from shapely.geometry import Polygon,LineString,Point
from common import require_schema,resources,digest

def footprint(p):
    x,y,z=p['position'];w,h,d=p['size'];a=math.radians(p['rotationY']);c,s=math.cos(a),math.sin(a)
    return Polygon([(x+c*u+s*v,z-s*u+c*v) for u,v in [(-w/2,-d/2),(w/2,-d/2),(w/2,d/2),(-w/2,d/2)]])
def validate_layout(data,strict=False):
    require_schema(data,'layout.schema.json');catalog,styles=resources();cat={x['id']:x for x in catalog['components']}
    errors=[];warnings=[];ids={};tol=1e-5
    from native import validate_assets
    validate_assets(data)
    def issue(kind,code,message,objects=None):
        (errors if kind=='error' else warnings).append({'code':code,'message':message,'ids':objects or []})
    for kind in ['rooms','walls','openings','placements']:
        seq=data[kind];ids[kind]={x['id']:x for x in seq}
        if len(ids[kind])!=len(seq):issue('error','duplicate-id',kind+' 存在重复 ID')
    cross=[x['id'] for kind in ['walls','placements'] for x in data[kind]]
    if len(cross)!=len(set(cross)):issue('error','duplicate-entity-id','墙体与家具不能共用同一个可编辑对象 ID')
    if data.get('lighting'):
        lights=data['lighting']['lights'];lids=[x['id'] for x in lights]
        if len(lids)!=len(set(lids)):issue('error','duplicate-light','光源ID重复')
        if sum(x['castShadow'] and x['enabled'] for x in lights)>3:issue('error','light-shadow-budget','实时投影射灯上限3个')
        for light in lights:
            if light['type']=='point' and light['castShadow']:issue('error','point-shadow-unsupported','点光不启用六面阴影，请使用射灯',[light['id']])
            if light['type']=='spot' and math.dist(light['position'],light['target'])<.05:issue('error','light-zero-target','光源与射灯目标重合',[light['id']])
            if light.get('anchorId') and light['anchorId'] not in ids['placements']:issue('error','unknown-light-anchor','绑定的灯具不存在',[light['id']])
    if data.get('customStyle'):
        from styles import validate_style
        validate_style(data['customStyle'])
        if data['customStyle']['id']!=data['styleId']:raise ValueError('customStyle 与 styleId 不一致')
    if not data.get('customStyle') and data['styleId'] not in [s['id'] for s in styles['styles']]:issue('error','unknown-style','未知 styleId')
    floor=Polygon(data['floor']['outline'])
    if not floor.is_valid or floor.area<.01:raise ValueError('floor.outline 自交或面积为零')
    rooms={}
    for r in data['rooms']:
        poly=Polygon(r['polygon']);rooms[r['id']]=poly
        if not poly.is_valid or poly.area<.01:issue('error','invalid-room','房间多边形不闭合有效或面积为零',[r['id']]);continue
        if not floor.buffer(tol).covers(poly):issue('error','room-outside-floor','房间边界超出楼面',[r['id']])
        if r.get('frontWallId') and r['frontWallId'] not in ids['walls']:issue('error','unknown-front-wall','正视参考墙不存在',[r['id']])
        if any(x not in ids['placements'] for x in r['subjectIds']):issue('error','unknown-subject','主体 ID 不存在',[r['id']])
        elif any(ids['placements'][x]['roomId']!=r['id'] for x in r['subjectIds']):issue('error','subject-room-mismatch','主体不属于当前房间',[r['id']])
    for i,(a,pa) in enumerate(rooms.items()):
        for b,pb in list(rooms.items())[i+1:]:
            if pa.is_valid and pb.is_valid and pa.intersection(pb).area>.005:issue('error','overlapping-rooms','房间区域重叠，不应同时计入两间房面积',[a,b])
    wall_lines={};wall_polys={}
    for w in data['walls']:
        line=LineString([w['a'],w['b']]);wall_lines[w['id']]=line;wall_polys[w['id']]=line.buffer(w['thickness']/2,cap_style=2)
        if line.length<.01:issue('error','zero-wall','墙长度为零',[w['id']])
        if w['height']>data['floor']['height']+.001:issue('error','wall-above-ceiling','墙高超过层高',[w['id']])
        if not floor.buffer(.001).covers(wall_polys[w['id']]):issue('error','wall-outside-floor','完整墙厚超出楼面，请检查描线或楼面外边界',[w['id']])
    for i,(a,pa) in enumerate(wall_lines.items()):
        for b,pb in list(wall_lines.items())[i+1:]:
            if pa.intersection(pb).length>.01:issue('error','duplicate-wall','同一墙段被重复定义',[a,b])
    graph=defaultdict(set);host_intervals=defaultdict(list);doors=[]
    for o in data['openings']:
        if o['wallId'] not in ids['walls']:issue('error','missing-host','门窗必须引用真实宿主墙',[o['id']]);continue
        w=ids['walls'][o['wallId']];line=wall_lines[w['id']];start=o['offset'];end=start+o['width']
        if w['kind']=='railing':issue('error','railing-opening-unsupported','连续栏杆不支持直接嵌入开口；请把栏杆拆为开口两侧的独立段',[o['id']])
        if end>line.length+.001 or o['sill']+o['height']>w['height']+.001:issue('error','opening-out-of-bounds','门窗尺寸超出墙',[o['id']])
        for a,b,id0,y0,y1 in host_intervals[w['id']]:
            if min(b,end)-max(a,start)>.001 and min(y1,o['sill']+o['height'])-max(y0,o['sill'])>.001:issue('error','overlapping-openings','同墙门窗相交',[id0,o['id']])
        host_intervals[w['id']].append((start,end,o['id'],o['sill'],o['sill']+o['height']))
        # Current compiler supports side-by-side apertures; vertically stacked apertures need one combined opening.
        if any(min(b,end)-max(a,start)>.001 and id0!=o['id'] for a,b,id0,_,_ in host_intervals[w['id']]):issue('error','stacked-openings-unsupported','同一横向区间有叠层开口；请合并开口或拆分墙段',[o['id']])
        conn=o.get('connects')
        if conn:
            if any(x is not None and x not in rooms for x in conn):issue('error','unknown-connection-room','门连接的房间不存在',[o['id']])
            elif conn[0]==conn[1]:issue('error','same-room-door','门两侧不能是同一房间',[o['id']])
            else:
                for x in conn:
                    if x is not None and rooms[x].boundary.distance(line.interpolate(start+o['width']/2))>w['thickness']+.05:issue('error','wrong-door-connection','门不在声明房间的边界上',[o['id'],x])
                if o['type'] in ['door','sliding-door','passage']:
                    graph[conn[0]].add(conn[1]);graph[conn[1]].add(conn[0]);doors.append((o,line))
        if not conn:issue('warning','missing-connection','开口未声明两侧空间；不从外观猜测目标',[o['id']])
        if o['type'] in ['door','sliding-door'] and 'openFraction' not in o:issue('warning','opening-state-unspecified','开合未确认；仅采用明确标注的关闭预览默认值',[o['id']])
    for c in data['openConnections']:
        a,b=c['rooms'];line=LineString(c['span'])
        if a not in rooms or b not in rooms:issue('error','unknown-open-connection','开放连接引用未知房间',c['rooms']);continue
        if a==b or line.length<.05:issue('error','invalid-open-connection','开放连接须有两间房和实际长度',c['rooms'])
        if not rooms[a].boundary.buffer(.02).covers(line) or not rooms[b].boundary.buffer(.02).covers(line):issue('error','open-connection-not-shared','开放连接不在两房共同边界',c['rooms'])
        # Do not call a solid wall a doorway in JSON.
        if any(line.buffer(.02).intersection(wp).area>line.length*.02 for wp in wall_polys.values()):issue('error','open-connection-blocked','开放连接穿过了实体墙，应登记真正门洞',c['rooms'])
        graph[a].add(b);graph[b].add(a)
    if None in graph:
        seen={None};queue=deque([None])
        while queue:
            for nxt in graph[queue.popleft()]-seen:seen.add(nxt);queue.append(nxt)
        for r in rooms:
            if r not in seen:issue('error','unreachable-room','从入户无法经已声明真实门/开放边到达',[r])
    else:issue('warning','entry-not-defined','未指定入户连接；不伪造可达性通过结论')
    polys={}
    for p in data['placements']:
        if p['componentId'] not in cat:issue('error','unknown-component','组件库中不存在该 componentId',[p['id']]);continue
        if p['roomId'] not in rooms:issue('error','unknown-room','家具房间 ID 不存在',[p['id']]);continue
        poly=footprint(p);polys[p['id']]=poly;meta=cat[p['componentId']]
        if not floor.buffer(.001).covers(poly):issue('error','object-outside-floor','家具完整占地超出楼面，不在下游偷偷搬回',[p['id']])
        if not rooms[p['roomId']].buffer(.025).covers(poly):issue('warning','object-crosses-room','家具占地越出所属功能区，请核对开放空间归属',[p['id']])
        low,high=meta['dimensionFactorRange']
        if not p.get('nativeAssetId') and any(not low<=s/b<=high for s,b in zip(p['size'],meta['defaultSize'])):issue('error','component-resize-range','组件缩放超过已支持范围；选同类组件或扩充库，不静默拉伸',[p['id']])
        if p['position'][1]<-.05 or p['position'][1]+p['size'][1]>data['floor']['height']+.01:issue('error','object-vertical-bounds','对象超出地板/天花边界',[p['id']])
        if meta['support']=='floor' and meta['category'] not in ['rug','table-lamp']:
            # Structural intersection is a useful warning; entrance blockage is reviewed explicitly.
            overlap=[wid for wid,wp in wall_polys.items() if poly.intersection(wp).area>.015]
            if overlap:issue('warning','object-wall-intersection','家具与墙体包络相交，请核对门洞或安装方式',[p['id'],*overlap])
    for i,a in enumerate(data['placements']):
        if a['id'] not in polys or cat.get(a['componentId'],{}).get('category') in ['rug','curtain','art']:continue
        for b in data['placements'][i+1:]:
            if b['id'] not in polys or cat.get(b['componentId'],{}).get('category') in ['rug','curtain','art']:continue
            vertical=min(a['position'][1]+a['size'][1],b['position'][1]+b['size'][1])-max(a['position'][1],b['position'][1])
            if vertical>.08 and polys[a['id']].intersection(polys[b['id']]).area>.045:issue('warning','object-overlap','对象包络相交；曲面/组合例外需人工核对',[a['id'],b['id']])
    for o,line in doors:
        if line.length<.01:continue
        a=line.interpolate(o['offset']);b=line.interpolate(o['offset']+o['width']);corridor=LineString([a,b]).buffer(.32,cap_style=2)
        for p in data['placements']:
            if p['id'] not in polys or p['position'][1]>.25 or cat.get(p['componentId'],{}).get('category') in ['rug','curtain','art']:continue
            if corridor.intersection(polys[p['id']]).area>.04:issue('warning','door-clearance','门前通行带与家具占地相交',[o['id'],p['id']])
    result={'schema':'interior.validation/1','layoutHash':digest(data),'ok':not errors,'errors':errors,'warnings':warnings,'measurements':{'floorArea':round(floor.area,4),'roomAreas':{k:round(v.area,4) for k,v in rooms.items()}}}
    # Only an unusable data reference/unsupported representation stops compilation.
    # Design observations stay visible in the report and never discard the draft.
    technical={'duplicate-id','duplicate-entity-id','duplicate-light','unknown-style','invalid-room','zero-wall','missing-host','unknown-component','unknown-room','unknown-front-wall','unknown-subject','unknown-light-anchor','stacked-openings-unsupported','railing-opening-unsupported'}
    fatal=[x for x in errors if x['code'] in technical]
    result['technicalErrors']=fatal
    result['compilable']=not fatal
    result['note']='业务观察不阻断草稿；发现错误回到源图、坐标、宿主或布局规则修改。'
    if strict and fatal:raise ValueError('\n'.join(x['code']+': '+x['message']+' '+','.join(x['ids']) for x in fatal))
    return result
