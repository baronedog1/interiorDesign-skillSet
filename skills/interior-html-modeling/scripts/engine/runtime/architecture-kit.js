

/* Explicit walls, openings and complete roof. The dollhouse cutaway is display-only. */
(function(C,T){
'use strict';
const H=window.PROJECT?.floor?.height||2.85;C.H=H;

const cutMats=new Map();
C.resetArchitectureMaterials=function(){for(const m of cutMats.values())m.dispose();cutMats.clear();};
function clipGroup(g,height){if(height===null)return;const plane=new T.Plane(new T.Vector3(0,-1,0),height);g.traverse(o=>{if(!o.isMesh)return;const old=o.material,key=old.uuid+'-'+height;let m=cutMats.get(key);if(!m){m=old.clone();m.clippingPlanes=[plane];m.clipShadows=true;cutMats.set(key,m);}o.material=m;});}
C.doors=[];
function openingAssembly(g,o,t){
 const a=o.assembly;if(!a)throw Error('缺少编译门窗状态 '+o.id);
 const group=C.group(g,'门窗 '+o.id);group.userData.openingId=o.id;
 if(o.type!=='passage'){
  for(const x of[o.c-o.w/2,o.c+o.w/2])C.box(group,.045,o.h,.07,x,o.b+o.h/2,0,C.M.bronze,.004,'洞口边框');
  for(const y of[o.b,o.b+o.h])C.box(group,o.w,.04,.07,o.c,y,0,C.M.bronze,.004,'洞口横框');
 }
 for(const p of a.panels){
  const leaf=C.group(group,'按源状态装配的扇',...p.center,p.yaw),[w,h,d]=p.size;
  let mat=p.infill==='solid'?C.M.cream:C.M.glass;
  if(p.infill==='frosted-glass'){mat=C.M.glass.clone();mat.transparent=false;mat.opacity=1;mat.roughness=.9;mat.color.set('#d9dedc');}
  C.box(leaf,w,h,d,0,0,0,mat,.002,'门窗填充');
  for(const x of[-w/2,w/2])C.box(leaf,.025,h,.035,x,0,0,C.M.bronze,.003,'扇竖框');
  for(const y of[-h/2,h/2])C.box(leaf,w,.025,.035,0,y,0,C.M.bronze,.003,'扇横框');
  if(o.type==='door'||o.type==='sliding')C.box(leaf,.022,.15,.045,w/2-.09,-.05,.04,C.M.bronze,.006,'门把手');
 }
 return group;
}
C.curtain=function(parent,width,height,x,y,z,rot=0){
 const g=C.group(parent,'双层落地窗帘',x,y,z,rot);
 for(const s of [-1,1]){
  const ww=width*.235,cx=s*(width/2-ww*.45);let geo=new T.PlaneGeometry(ww,height,36,44),p=geo.attributes.position;
  for(let i=0;i<p.count;i++){const u=(p.getX(i)/ww+.5),v=(p.getY(i)/height+.5);p.setZ(i,Math.cos(u*Math.PI*10)*(.065+.012*(1-v)));p.setY(i,p.getY(i)+.006*Math.cos(u*20)*(1-v));}
  geo.computeVertexNormals();const m=C.mesh(g,geo,C.M.linen,'真实波褶亚麻帘',cx,height/2,0);m.material=C.M.linen.clone();m.material.side=T.DoubleSide;
 }
 const sh=new T.PlaneGeometry(width*.98,height-.02,70,30),p=sh.attributes.position;
 for(let i=0;i<p.count;i++)p.setZ(i,.035*Math.cos(p.getX(i)*38)-.07);sh.computeVertexNormals();
 C.mesh(g,sh,C.M.sheer,'透光内纱',0,height/2,-.06);
 C.box(g,width+.2,.055,.035,0,height+.025,0,C.M.cream,.015,'双轨窗帘滑轨');
 return g;
};
function wall(parent,id,ax,az,bx,bz,t,openings=[],cut=.92,wallHeight=C.H,footprint=null){
 const H=wallHeight;const L=Math.hypot(bx-ax,bz-az),g=C.group(parent,id,ax,0,az,-Math.atan2(bz-az,bx-ax));
 const ops=openings.sort((a,b)=>a.c-b.c);let from=0;
 const u=[(bx-ax)/L,(bz-az)/L],n=[-u[1],u[0]],poly=footprint?footprint.map(p=>[(p[0]-ax)*u[0]+(p[1]-az)*u[1],(p[0]-ax)*n[0]+(p[1]-az)*n[1]]):[[0,t/2],[L,t/2],[L,-t/2],[0,-t/2]];
 const clip=(points,x,keep)=>{const out=[];for(let i=0;i<points.length;i++){const a=points[i],b=points[(i+1)%points.length],ia=keep*(a[0]-x)>=-1e-9,ib=keep*(b[0]-x)>=-1e-9;if(ia)out.push(a);if(ia!==ib){const f=(x-a[0])/(b[0]-a[0]);out.push([x,a[1]+(b[1]-a[1])*f]);}}return out;};
 const solid=(start,end,bottom,top,material=C.M.plaster)=>{if(end-start<.000001||top-bottom<.000001)return;let points=poly;if(start>1e-7)points=clip(points,start,1);if(end<L-1e-7)points=clip(points,end,-1);if(points.length<3)return;const shape=new T.Shape();points.forEach((p,i)=>i?shape.lineTo(p[0],-p[1]):shape.moveTo(p[0],-p[1]));shape.closePath();const geo=new T.ExtrudeGeometry(shape,{depth:top-bottom,bevelEnabled:false,steps:1});geo.rotateX(-Math.PI/2);geo.translate(0,bottom,0);C.mesh(g,geo,material,id+' · 联接墙实体');};
 const skirting=()=>{}; // No independent rounded strips crossing joined wall corners.
 for(const o of ops){const a=o.c-o.w/2,b=o.c+o.w/2;solid(from,a,0,H);skirting(from,a);solid(a,b,0,o.b);solid(a,b,o.b+o.h,H);if(o.b>0)skirting(a,b);
  openingAssembly(g,o,t);
  const fact=o.assembly;if(fact.type==='passage'&&fact.passageShape&&fact.passageShape!=='rect'){const top=x=>{const h=o.h,w=o.w;if(fact.passageShape==='arch'){const rise=fact.archRise??Math.min(.6,h/2);return h-rise+rise*Math.sqrt(Math.max(0,1-((x-w/2)/(w/2))**2));}const l=fact.cornerLeft??.25,r=fact.cornerRight??.25;if(x<l)return h-l+Math.sqrt(Math.max(0,l*l-(x-l)**2));if(x>w-r)return h-r+Math.sqrt(Math.max(0,r*r-(x-(w-r))**2));return h;};const shape=new T.Shape();shape.moveTo(a,o.b+o.h);for(let i=0;i<=96;i++){const x=o.w*i/96;shape.lineTo(a+x,o.b+top(x));}shape.lineTo(b,o.b+o.h);shape.closePath();const geo=new T.ExtrudeGeometry(shape,{depth:t,bevelEnabled:false,steps:1});geo.translate(0,0,-t/2);const cap=C.mesh(g,geo,C.M.plaster,'异形洞口墙实体');cap.userData.openingId=o.id;}

  from=b;
 }
 solid(from,L,0,H);skirting(from,L);

 clipGroup(g,cut);return g;
}
function floorArea(parent,bounds,kind,name){
 const [x0,x1,z0,z1]=bounds,w=x1-x0,d=z1-z0,g=C.group(parent,name);
 C.box(g,w,.04,d,(x0+x1)/2,-.024,(z0+z1)/2,kind==='wood'?C.M.walnut:C.M.travertine);
 if(kind==='wood'){
  const buckets=Array.from({length:7},()=>[]),pw=.178,len=1.38;
  for(let z=z0;z<z1-.01;z+=pw){const dep=Math.min(pw,z1-z),offset=C.rand()*len;for(let x=x0-offset;x<x1;x+=len){const a=Math.max(x,x0),b=Math.min(x+len,x1);if(b-a<.007)continue;buckets[Math.floor(C.rand()*7)].push([a,b,z,dep]);}}
  for(let k=0;k<7;k++){
   const m=C.M.oak.clone();m.userData.cmfMultiplier=1+(k-3)*.022;m.color.copy(C.M.oak.color).multiplyScalar(1+(k-3)*.022);m.name='风格木地板 · 色差 '+k;
   const inst=new T.InstancedMesh(new T.BoxGeometry(1,.022,1),m,buckets[k].length),dummy=new T.Object3D();
   buckets[k].forEach(([a,b,z,dep],i)=>{dummy.position.set((a+b)/2,-.002,z+dep/2);dummy.scale.set(b-a-.0015,1,dep-.0015);dummy.updateMatrix();inst.setMatrixAt(i,dummy.matrix);});inst.receiveShadow=true;inst.name='错缝长条橡木 / 实体分板';g.add(inst);
  }
 }else{
  const tile=.64;for(let x=x0;x<x1-.01;x+=tile)for(let z=z0;z<z1-.01;z+=tile){const w=Math.min(tile,x1-x),d=Math.min(tile,z1-z);C.box(g,w-.003,.018,d-.003,x+w/2,-.001,z+d/2,C.M.travertine,.004,'洞石地砖 / 3mm美缝');}
 }
}

C.buildWall=wall;C.buildFloorRect=floorArea;C.applyCut=clipGroup;
})(window.CREAM,window.THREE);
