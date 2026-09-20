/* Parametric joinery. Metres; local +Z is the operating/front face.
   Methods construct geometry; they do not score, reject or gate a design. */
(function(global){'use strict';
 const clone=x=>JSON.parse(JSON.stringify(x)), num=(x,d)=>Number.isFinite(x)?x:d;
 function doorWidths(width,count,gap){return Array.from({length:count},()=> (width-gap*(count+1))/count);}
 function divide(width,opts={}){
  const gap=num(opts.gap,.002),min=num(opts.minDoor,.30),max=num(opts.maxDoor,.50),doubleMin=num(opts.doubleMin,.35);
  // These are adjustable starting values, never an acceptance threshold.
  for(let n=Math.max(1,Math.ceil(width/(max+2*gap)));n<=Math.ceil(width/(min+gap))+1;n++){
   for(let pairs=Math.floor(n/2);pairs>=0;pairs--){const singles=n-2*pairs,modules=pairs+singles,actual=(width-gap*(n+modules))/n;
    if(actual<min||actual>max||(pairs&&actual<doubleMin))continue;
    return [...Array.from({length:pairs},()=>({width:actual*2+3*gap,doors:2})),...Array.from({length:singles},()=>({width:actual+2*gap,doors:1}))];
   }
  }
  return [{width,doors:1,note:'按当前宽度表达；门型、五金或相邻分格待设计适配'}];
 }
 function parts(spec){
  const [w,h,d]=spec.size,j=spec.joinery||{},kind=j.kind||'cabinet', t=num(j.board,.018),g=num(j.gap,.002),front=d/2,back=-d/2, out=[];
  const add=(name,size,pos,material='body',role='fixed',extra={})=>{if(size.every(v=>v>0&&Number.isFinite(v)))out.push({name,size,position:pos,material,role,...extra});};
  const panel=(name,x,y,z,sx,sy,sz,mat='body',role='fixed',extra={})=>add(name,[sx,sy,sz],[x,y,z],mat,role,extra);
  function slab(name,width,depth,y,thickness,holes=[],mat='top'){
   const xs=[-width/2,width/2],zs=[-depth/2,depth/2];
   for(const q of holes){if(q.x-q.width/2>=width/2||q.x+q.width/2<=-width/2||q.z-q.depth/2>=depth/2||q.z+q.depth/2<=-depth/2)continue;xs.push(Math.max(-width/2,q.x-q.width/2),Math.min(width/2,q.x+q.width/2));zs.push(Math.max(-depth/2,q.z-q.depth/2),Math.min(depth/2,q.z+q.depth/2));}
   const xx=[...new Set(xs)].sort((a,b)=>a-b),zz=[...new Set(zs)].sort((a,b)=>a-b);
   for(let a=1;a<xx.length;a++)for(let b=1;b<zz.length;b++){const x=(xx[a]+xx[a-1])/2,z=(zz[b]+zz[b-1])/2;
    if(holes.some(q=>Math.abs(x-q.x)<q.width/2&&Math.abs(z-q.z)<q.depth/2))continue;
    panel(name,x,y,z,xx[a]-xx[a-1],thickness,zz[b]-zz[b-1],mat,'surface');}
  }
  function fronts(x,width,bottom,top,doors=2,role='door'){
   const usable=top-bottom;if(usable<=0)return;
   const widths=doorWidths(width,doors,g);let edge=x-width/2+g;
   for(let i=0;i<doors;i++){
    const dw=widths[i],cx=edge+dw/2,hinge=i%2?'right':'left';
    panel(role==='fixed'?'固定饰面':'活动门',cx,(bottom+top)/2,front-t/2,dw,usable,t,'front',role,{hinge,openAngle:num(j.openAngle,0)*(hinge==='right'?1:-1)});
    if(j.handle==='pull'&&role==='door')panel('外露拉手',cx+(hinge==='left'?1:-1)*(dw/2-.045),(bottom+top)/2,front+.012,.012,.12,.024,'metal');
    edge+=dw+g;
   }
  }
  function drawers(x,width,bottom,top,count){
   const step=(top-bottom)/count,slot=j.handle==='recess'?num(j.recessHeight,.025):0;
   for(let i=0;i<count;i++){
    const y=bottom+i*step,fh=step-g-slot,innerD=d-2*t-num(j.drawerBackClearance,.035),z=back+t+innerD/2;
    panel('抽面',x,y+fh/2,front-t/2,width-2*g,fh,t,'front','drawer');
    panel('抽箱底',x,y+t/2,z,width-4*t,t,innerD,'body','drawer');
    for(const sign of [-1,1])panel('抽箱侧板',x+sign*(width/2-1.5*t),y+fh/2,z,t,fh-t,innerD,'body','drawer');
    panel('抽箱背板',x,y+fh/2,back+1.5*t,width-4*t,fh-t,t,'body','drawer');
    if(slot){panel('内凹扣手槽背',x,y+fh+slot/2,front-t-num(j.recessDepth,.025),width-2*g,slot,t/3,'dark');panel('扣手槽下折边',x,y+fh,front-t-num(j.recessDepth,.025)/2,width-2*g,t/3,num(j.recessDepth,.025),'dark');}
   }
  }
  if(kind==='surface'){
   slab('连续台面',w,d,h/2,h,j.holes||[]);return out;
  }
  if(kind==='ceiling'){
   const tiles=j.tiles,tx=tiles?num(tiles[0],.6):w,tz=tiles?num(tiles[1],.6):d;
   for(let x=-w/2;x<w/2-1e-6;x+=tx)for(let z=-d/2;z<d/2-1e-6;z+=tz){const sx=Math.min(tx,w/2-x),sz=Math.min(tz,d/2-z);panel('吊顶面板',x+sx/2,t/2,z+sz/2,sx-(tiles?g:0),t,sz-(tiles?g:0),'plaster','ceiling');}
   if(j.fascia!==false){for(const z of [back+t/2,front-t/2])panel('吊顶封边',0,(h+t)/2,z,w,h-t,t,'plaster','ceiling');for(const x of [-w/2+t/2,w/2-t/2])panel('吊顶侧封边',x,(h+t)/2,0,t,h-t,d-2*t,'plaster','ceiling');}
   return out;
  }
  if(kind==='desk'){
   slab('桌面',w,d,h-t/2,t,j.holes||[]);
   const dh=num(j.drawerHeight,0),legH=h-t-dh-g;
   for(const x of [-w/2+t/2,w/2-t/2])panel('桌侧支承',x,legH/2,0,t,legH,d);
   if(dh>0){const count=Math.max(1,num(j.drawers,1));for(let i=0;i<count;i++)drawers(-w/2+(i+.5)*w/count,w/count,h-t-g-dh,h-t-g,1);}return out;
  }
  if(kind==='platform'||kind==='banquette'){
   const cushion=num(j.cushionThickness,kind==='platform'?.12:.06),seat=num(j.seatHeight,h),base=seat-cushion;
   if(j.storage||kind==='banquette'){out.push(...parts({...spec,size:[w,base,d],joinery:{...j,kind:'cabinet',zones:undefined,doors:j.doors||2,top:true}}));}else panel('承托底座',0,base/2,0,w,base,d);panel('连续软垫',0,base+cushion/2,0,w-2*g,cushion,d-2*g,'fabric','cushion');
   if(j.backrestHeight)panel('落台靠背',0,base+j.backrestHeight/2,back+num(j.backrestDepth,.08)/2,w,j.backrestHeight,num(j.backrestDepth,.08),'fabric');
   if(j.headboardHeight)panel('整块床头挡板',0,base+j.headboardHeight/2,back-t/2,w,j.headboardHeight,t,'front');return out;
  }
  const plinth=num(j.plinthHeight,.08),bottom=num(j.bottom,plinth),carcassTop=h-num(j.topThickness,0),innerD=d-t;
  for(const x of [-w/2+t/2,w/2-t/2])panel('柜侧板',x,(carcassTop+bottom)/2,-t/2,t,carcassTop-bottom,innerD);
  if(j.back!==false)panel('柜背板',0,(carcassTop+bottom)/2,back+t/2,w-2*t,carcassTop-bottom,t);
  if(kind!=='housing')panel('柜底板',0,bottom+t/2,-t/2,w-2*t,t,innerD);
  if(j.top!==false)panel('柜顶板',0,carcassTop-t/2,-t/2,w-2*t,t,innerD);
  if(plinth>0&&kind!=='housing'){
   const retreat=num(j.plinthInset,.05);panel('内缩踢脚',0,plinth/2,front-t-retreat,w-2*t,plinth,t);
   if(j.exposedBack)panel('背侧踢脚',0,plinth/2,back+retreat,w-2*t,plinth,t);
   if(j.exposedLeft)panel('左侧踢脚',-w/2+retreat,plinth/2,0,t,plinth,d-2*retreat);
   if(j.exposedRight)panel('右侧踢脚',w/2-retreat,plinth/2,0,t,plinth,d-2*retreat);
  }
  const blind=num(j.blindWidth,0),side=j.blindSide==='right'?1:-1,activeW=w-blind,activeX=-side*blind/2;
  if(blind)panel('转角固定盲板',side*(w-blind)/2,(bottom+carcassTop)/2,front-t/2,blind-g,carcassTop-bottom,t,'front','fixed');
  const doorBottom=num(j.doorBottom,bottom+g),doorTop=num(j.doorTop,carcassTop-g);
  const zones=j.zones||[{bottom:doorBottom,top:doorTop,type:kind==='housing'?'open':(j.drawers?'drawers':'doors'),count:j.drawers||j.doors||2}];
  for(let n=0;n<zones.length;n++){
   const z=zones[n],lo=num(z.bottom,doorBottom),hi=num(z.top,doorTop);
   if(n&&z.shelf!==false)panel('分区层板',activeX,lo-t/2,-t/2,activeW-2*t,t,innerD-t);
   if(z.type==='drawers')drawers(activeX,activeW,lo,hi,z.count||1);
   else if(z.type==='doors'||z.type==='fixed')fronts(activeX,activeW,lo,hi,z.count||1,z.type==='fixed'?'fixed':'door');
  }
  for(const y of j.shelves||[])panel('可调层板',0,y,0,w-2*t,t,d-2*t);
  if(j.exposedBack)panel('完整固定背饰面',0,(bottom+carcassTop)/2,back-t/2,w,carcassTop-bottom,t,'front','fixed');
  if(j.topThickness)slab('台面',w,d,h-j.topThickness/2,j.topThickness,j.holes||[]);
  for(const q of j.holes||[]){if(q.kind!=='sink')continue;const dep=num(q.basinDepth,.18),bt=num(q.basinWall,.012),y=h-num(j.topThickness,0)-dep;
   panel('盆底',q.x,y+bt/2,q.z,q.width,bt,q.depth,'basin');for(const sign of [-1,1]){panel('盆侧壁',q.x+sign*(q.width-bt)/2,y+dep/2,q.z,bt,dep,q.depth,'basin');panel('盆端壁',q.x,y+dep/2,q.z+sign*(q.depth-bt)/2,q.width-2*bt,dep,bt,'basin');}}
  return out;
 }
 function solve(input){const p=clone(input),map=new Map((p.placements||[]).map(x=>[x.id,x])),done=new Set(),active=new Set();
  function visit(a){if(done.has(a.id)||active.has(a.id))return;active.add(a.id);const rel=a.joinery?.anchor,b=rel&&map.get(rel.id);if(b&&!active.has(b.id)){visit(b);const ang=(b.rotationY||0)*Math.PI/180,dx=num(rel.x,0)+(rel.face==='right'?(b.size[0]+a.size[0])/2:rel.face==='left'?-(b.size[0]+a.size[0])/2:0),dz=num(rel.z,0)+(rel.face==='front'?(b.size[2]-a.size[2])/2:rel.face==='back'?-(b.size[2]-a.size[2])/2:0);a.rotationY=b.rotationY||0;a.position[0]=b.position[0]+Math.cos(ang)*dx+Math.sin(ang)*dz;a.position[2]=b.position[2]-Math.sin(ang)*dx+Math.cos(ang)*dz;a.position[1]=b.position[1]+(rel.face==='top'?b.size[1]:0)+num(rel.y,0);if(rel.width)a.size[0]=b.size[0]+num(rel.widthOffset,0);if(rel.depth)a.size[2]=b.size[2]+num(rel.depthOffset,0);if(rel.toHeight!==undefined)a.size[1]=rel.toHeight-a.position[1];}
   active.delete(a.id);done.add(a.id);}
  for(const a of map.values())visit(a);
  for(const a of map.values()){
   const ids=a.joinery?.spanIds;if(!ids?.length)continue;const members=ids.map(id=>map.get(id)).filter(Boolean);if(!members.length)continue;
   const theta=(members[0].rotationY||0)*Math.PI/180,c=Math.cos(theta),s=Math.sin(theta),bounds=[];
   for(const b of members){const cx=c*b.position[0]-s*b.position[2],cz=s*b.position[0]+c*b.position[2];bounds.push({x0:cx-b.size[0]/2,x1:cx+b.size[0]/2,z0:cz-b.size[2]/2,z1:cz+b.size[2]/2,y:b.position[1]+b.size[1]});}
   const x0=Math.min(...bounds.map(b=>b.x0)),x1=Math.max(...bounds.map(b=>b.x1)),z0=Math.min(...bounds.map(b=>b.z0)),z1=Math.max(...bounds.map(b=>b.z1)),x=(x0+x1)/2,z=(z0+z1)/2;
   a.position=[c*x+s*z,Math.max(...bounds.map(b=>b.y))+num(a.joinery.yOffset,0),-s*x+c*z];a.size[0]=x1-x0;a.size[2]=z1-z0;a.rotationY=members[0].rotationY||0;
   for(const hole of a.joinery.holes||[]){const b=map.get(hole.anchorId);if(b){hole.x=c*b.position[0]-s*b.position[2]-x+num(hole.offsetX,0);hole.z=s*b.position[0]+c*b.position[2]-z+num(hole.offsetZ,0);}}
  }return p;
 }
 
 function run(layout,request){
  const p=clone(layout),origin=request.position||[0,0,0],angle=(request.rotationY||0)*Math.PI/180;
  const modules=request.modules||divide(request.width,request.doorRange||{}), total=modules.reduce((a,m)=>a+m.width,0),id=request.id;
  const old=new Set((p.placements||[]).filter(a=>a.joinery?.runId===id).map(a=>a.id));p.placements=p.placements.filter(a=>!old.has(a.id));let x=-total/2;
  modules.forEach((m,i)=>{const dx=x+m.width/2; p.placements.push({id:id+'-'+(i+1),name:m.name||'定制柜 '+(i+1),roomId:request.roomId,componentId:m.componentId||'cabinet.custom',position:[origin[0]+Math.cos(angle)*dx,origin[1],origin[2]-Math.sin(angle)*dx],size:[m.width,m.height||request.height,m.depth||request.depth],rotationY:request.rotationY||0,joinery:{...(request.joinery||{}),...(m.joinery||{}),doors:m.doors||m.joinery?.doors||2,runId:id}});x+=m.width;});
  if(request.worktop){const top=request.worktop;p.placements.push({id:id+'-top',name:'整组连续台面',roomId:request.roomId,componentId:'surface.worktop',position:[origin[0],origin[1]+request.height,origin[2]],size:[total,top.thickness||.03,request.depth],rotationY:request.rotationY||0,joinery:{kind:'surface',runId:id,spanIds:modules.map((m,i)=>id+'-'+(i+1)),holes:top.holes||[]}});}
  return solve(p);
 }
 const api={parts,divide,doorWidths,solve,run};global.InteriorJoinery=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
