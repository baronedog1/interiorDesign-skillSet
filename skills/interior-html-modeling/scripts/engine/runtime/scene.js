/* Pure scene compilation. PROJECT is the only source of architecture and placements. */
(function(C,T){'use strict';
 function polygonArea(poly){let a=0;for(let i=0;i<poly.length;i++){const p=poly[i],q=poly[(i+1)%poly.length];a+=p[0]*q[1]-q[0]*p[1];}return Math.abs(a)/2;}
 // Keep light/label positions inside concave room polygons (bbox centres may be outside).
 function internalPoint(poly){
  const inside=(x,z)=>{let yes=false;for(let i=0,j=poly.length-1;i<poly.length;j=i++){const a=poly[i],b=poly[j];if((a[1]>z)!=(b[1]>z)&&x<(b[0]-a[0])*(z-a[1])/(b[1]-a[1])+a[0])yes=!yes;}return yes;};
  const xs=poly.map(p=>p[0]),zs=poly.map(p=>p[1]),x0=Math.min(...xs),x1=Math.max(...xs),z0=Math.min(...zs),z1=Math.max(...zs),cx=(x0+x1)/2,cz=(z0+z1)/2;
  if(inside(cx,cz))return[cx,0,cz];let best=null,dist=Infinity;
  for(let i=0;i<21;i++)for(let j=0;j<21;j++){const x=x0+(i+.5)*(x1-x0)/21,z=z0+(j+.5)*(z1-z0)/21,d=(x-cx)**2+(z-cz)**2;if(inside(x,z)&&d<dist){best=[x,0,z];dist=d;}}
  if(!best)throw Error('Room polygon has no stable interior point');return best;
 }
 function polygonMesh(parent,poly,y,material,name){const s=new T.Shape();poly.forEach((p,i)=>i?s.lineTo(p[0],-p[1]):s.moveTo(p[0],-p[1]));s.closePath();const mesh=C.mesh(parent,new T.ShapeGeometry(s),material,name);mesh.rotation.x=-Math.PI/2;mesh.position.y=y;return mesh;}
 C.buildScene=function(root,P){
  const style=window.STYLE_CATALOG.styles.find(s=>s.id===P.styleId);if(!style)throw Error('未知风格 '+P.styleId);C.resetArchitectureMaterials();C.applyStyleRecipe(style);
  C.H=P.floor.height;C.assets=[];C.doors=[];const architecture=C.group(root,'01 建筑 / 门窗 / 基础'),walls=C.group(architecture,'完整墙体与洞口');C.architecture=architecture;
  const xs=P.floor.outline.map(p=>p[0]),zs=P.floor.outline.map(p=>p[1]);C.sceneBounds={minX:Math.min(...xs),maxX:Math.max(...xs),minZ:Math.min(...zs),maxZ:Math.max(...zs)};
  polygonMesh(architecture,P.floor.outline,-.03,C.M.walnut,'完整楼面');
  C.rooms=P.rooms.map(r=>{const xx=r.polygon.map(p=>p[0]),zz=r.polygon.map(p=>p[1]),bounds=[Math.min(...xx),Math.max(...xx),Math.min(...zz),Math.max(...zz)];return {...r,bounds,area:polygonArea(r.polygon),point:internalPoint(r.polygon)};});
  for(const r of C.rooms){const rect=r.polygon.length===4&&r.polygon.every(p=>(p[0]===r.bounds[0]||p[0]===r.bounds[1])&&(p[1]===r.bounds[2]||p[1]===r.bounds[3]));const kind=['kitchen','bathroom'].includes(r.type)?'stone':'wood';if(rect)C.buildFloorRect(architecture,r.bounds,kind,r.name+'地面');else polygonMesh(architecture,r.polygon,.004,kind==='wood'?C.M.oak:C.M.travertine,r.name+'地面');}
  for(const w of P.walls){const ops=P.openings.filter(o=>o.wallId===w.id).map(o=>({id:o.id,type:o.type==='sliding-door'?'sliding':['passage'].includes(o.type)?'passage':['window','fixed-glazing'].includes(o.type)?'window':'door',c:o.offset+o.width/2,w:o.width,b:o.sill,h:o.height}));let g;
   if(w.kind==='railing'){g=C.group(walls,w.name||w.id,w.a[0],0,w.a[1],-Math.atan2(w.b[1]-w.a[1],w.b[0]-w.a[0]));const L=Math.hypot(w.b[0]-w.a[0],w.b[1]-w.a[1]),h=w.height;C.box(g,L,.035,w.thickness,L/2,h,0,C.M.bronze,.007);for(let x=.04;x<L;x+=.16)C.box(g,.024,h,w.thickness,x,h/2,0,C.M.bronze,.004);C.applyCut(g,.92);}
   else g=C.buildWall(walls,w.name||w.id,...w.a,...w.b,w.thickness,ops,.92,w.height);
   g.userData.sourceId=w.id;g.userData.kind='wall';g.userData.openingIds=ops.map(o=>o.id);
  }
  const roof=C.group(root,'02 完整天花 / 灯槽');C.ceiling=roof;roof.visible=false;const ceilingMat=C.M.plaster.clone();ceilingMat.side=T.DoubleSide;polygonMesh(roof,P.floor.outline,P.floor.height,ceilingMat,'完整顶面');
  const groups=new Map();for(const r of C.rooms){const g=C.group(root,r.name);g.userData.roomId=r.id;groups.set(r.id,g);}
  for(const p of P.placements){const o=p.nativeAssetId?C.nativeAssets.create(groups.get(p.roomId),p):C.instantiate(groups.get(p.roomId),p,window.COMPONENT_CATALOG);if(!p.nativeAssetId&&p.materialOverrides)o.traverse(x=>{if(!x.material)return;const arr=Array.isArray(x.material)?x.material:[x.material];const next=arr.map(m=>{const patch=p.materialOverrides[m.name];if(!patch)return m;const a=m.clone();if(patch.color)a.color.set(patch.color);if(Number.isFinite(patch.roughness))a.roughness=patch.roughness;if(Number.isFinite(patch.metalness))a.metalness=patch.metalness;return a;});x.material=Array.isArray(x.material)?next:next[0];});}
  // Preview defaults are conveniences, not a separately accepted camera plan.
  const b=C.sceneBounds,cx=(b.minX+b.maxX)/2,cz=(b.minZ+b.maxZ)/2,d=Math.max(b.maxX-b.minX,b.maxZ-b.minZ);
  C.previewPresets={overview:{title:'全屋鸟瞰',pos:[cx+d*1.15,d*1.15,cz+d*1.42],target:[cx,.4,cz],fov:38},plan:{title:'正交平面',pos:[cx,d*2,cz+.001],target:[cx,0,cz],fov:38}};
  for(const r of C.rooms){const [a,b,c,d]=r.bounds,subject=P.placements.find(p=>r.subjectIds.includes(p.id)),target=subject?[subject.position[0],1.3,subject.position[2]]:[r.point[0],1.3,r.point[2]];C.previewPresets[r.id]={title:r.name,pos:[r.point[0],1.55,d-.35],target,fov:80};}
  if(window.PREVIEW_PRESETS)Object.assign(C.previewPresets,window.PREVIEW_PRESETS);
 };
})(window.CREAM,window.THREE);
