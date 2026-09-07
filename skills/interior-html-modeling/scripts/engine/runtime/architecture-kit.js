

/* Explicit walls, openings and complete roof. The dollhouse cutaway is display-only. */
(function(C,T){
'use strict';
const H=window.PROJECT?.floor?.height||2.85;C.H=H;

const cutMats=new Map();
C.resetArchitectureMaterials=function(){for(const m of cutMats.values())m.dispose();cutMats.clear();};
function clipGroup(g,height){if(height===null)return;const plane=new T.Plane(new T.Vector3(0,-1,0),height);g.traverse(o=>{if(!o.isMesh)return;const old=o.material,key=old.uuid+'-'+height;let m=cutMats.get(key);if(!m){m=old.clone();m.clippingPlanes=[plane];m.clipShadows=true;cutMats.set(key,m);}o.material=m;});}
C.doors=[];
function door(g,c,w,h,thick){
 const d=C.group(g,'门扇 · 可开合',c-w/2,0,0);d.rotation.y=1.3;C.doors.push(d);
 C.box(d,w-.035,h-.03,.044,w/2,h/2,0,C.M.cream,.016,'实木复合平板门');
 C.box(d,w-.14,h-.20,.01,w/2,h/2,.027,C.M.plaster,.006,'门扇内嵌细边');
 for(const side of [-1,1]){
  C.cyl(d,.028,.028,.013,w-.13,1.02,side*.035,C.M.bronze,24,'门锁底座').rotation.x=Math.PI/2;
  C.rod(d,[w-.13,1.02,side*.04],[w-.13,1.02,side*.092],.012,C.M.bronze);
  C.rod(d,[w-.13,1.02,side*.092],[w-.25,1.02,side*.092],.012,C.M.bronze,'杠杆式门把手');
 }
 for(const y of [.22,1.15,2.05])C.cyl(d,.014,.014,.09,.023,y,0,C.M.bronze,12,'金属合页');
 return d;
}
function windowDetail(g,o,t){
 const c=o.c,w=o.w,h=o.h,b=o.b;
 C.box(g,w+.13,.055,t+.18,c,b-.035,0,C.M.travertine,.008,'石材窗台');
 for(const xx of [c-w/2+.025,c+w/2-.025])C.box(g,.047,h,.072,xx,b+h/2,0,C.M.cream,.007,'窄边窗框');
 for(const yy of [b+.023,b+h-.023])C.box(g,w,.046,.072,c,yy,0,C.M.cream,.007,'窗框横樘');
 const cnt=Math.max(2,Math.round(w/.95));
 for(let i=0;i<cnt;i++){
  const xx=c-w/2+(i+.5)*w/cnt;
  C.box(g,w/cnt-.035,h-.07,.012,xx,b+h/2,0,C.M.glass,0,'独立玻璃窗扇');
  if(i>0)C.box(g,.027,h,.052,c-w/2+i*w/cnt,b+h/2,.006,C.M.bronze,.003,'窗扇竖梃');
 }
 C.box(g,.016,.13,.024,c+w/2-.10,b+h*.48,.052,C.M.bronze,.006,'窗把手');
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
function wall(parent,id,ax,az,bx,bz,t,openings=[],cut=.92,wallHeight=C.H){
 const H=wallHeight;const L=Math.hypot(bx-ax,bz-az),g=C.group(parent,id,ax,0,az,-Math.atan2(bz-az,bx-ax));
 const ops=openings.sort((a,b)=>a.c-b.c);let from=0;
 const solid=(start,end,bottom,top)=>{if(end-start>.005&&top-bottom>.005)C.box(g,end-start,top-bottom,t,(start+end)/2,(top+bottom)/2,0,C.M.plaster,.009,id+' · 墙实体');};
 const skirting=(start,end)=>{if(end-start<.01)return;for(const s of [-1,1])C.box(g,end-start,.075,.018,(start+end)/2,.047,s*(t/2+.009),C.M.cream,.004,'踢脚线 / 阴影缝');};
 for(const o of ops){const a=o.c-o.w/2,b=o.c+o.w/2;solid(from,a,0,H);skirting(from,a);solid(a,b,0,o.b);solid(a,b,o.b+o.h,H);if(o.b>0)skirting(a,b);
  if(o.type==='window')windowDetail(g,o,t);
  else if(o.type==='door'){
   for(const xx of [a-.023,b+.023])C.box(g,.058,o.h+.035,t+.055,xx,o.h/2,0,C.M.cream,.006,'细窄门套');
   C.box(g,o.w+.11,.065,t+.055,o.c,o.h+.025,0,C.M.cream,.006,'门套上横');
   door(g,o.c,o.w,o.h,t);
  }else if(o.type==='sliding'){
   C.box(g,o.w,.055,.11,o.c,o.h-.025,0,C.M.bronze,.004,'吊轨玻璃门');
   const sw=o.w*.51;const p=C.group(g,'厨房窄框长虹玻璃移门',a+sw/2,0,0);
   C.box(p,sw,o.h-.10,.014,0,o.h/2,0,C.M.glass);
   for(const xx of [-sw/2,sw/2])C.box(p,.025,o.h,.035,xx,o.h/2,0,C.M.bronze,.003);
   for(const yy of [.035,o.h-.035])C.box(p,sw,.028,.035,0,yy,0,C.M.bronze);
   for(let i=0;i<20;i++)C.box(p,.002,o.h-.1,.02,-sw/2+.015+i*sw/20,o.h/2,0,C.M.sheer);
   C.box(p,.019,.27,.05,sw/2-.08,1.05,.038,C.M.bronze,.009);
  }
  from=b;
 }
 solid(from,L,0,H);skirting(from,L);
 for(const s of [-1,1])C.box(g,L,.055,.035,L/2,H-.04,s*(t/2+.017),C.M.cream,.004,'顶面细收口');
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
