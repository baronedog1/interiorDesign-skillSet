/* Render the semantic parts at actual dimensions: no fit-bounds scaling. */
(function(C,T){'use strict';
 const defaults={wardrobe:{doors:2,plinthHeight:.08},upperCabinet:{doors:2,plinthHeight:0},counter:{doors:2},sink:{doors:2,top:false,topThickness:.03,holes:[{x:0,z:0,width:.50,depth:.38,kind:'sink'}]},hob:{drawers:2,top:false,topThickness:.03,holes:[{x:0,z:0,width:.50,depth:.38,kind:'hob'}]},sideboard:{doors:2},shelf:{zones:[{type:'open'}]},desk:{kind:'desk'},customCabinet:{},customDesk:{kind:'desk'},sleepPlatform:{kind:'platform'},ceilingAssembly:{kind:'ceiling'},worktop:{kind:'surface'},fridgeHousing:{kind:'housing'},banquette:{kind:'banquette'}};
 C.joinery={supports:(meta,p)=>!!p.joinery||!!defaults[meta.builder],build(parent,p,meta){
  const j={...(defaults[meta.builder]||{}),...(p.joinery||{})},g=C.group(parent,p.name||meta.name);
  const materials={body:C.M.oak,front:C.M.cream,top:C.M.travertine,dark:C.M.dark,metal:C.M.bronze,fabric:C.M.linen,plaster:C.M.plaster,basin:C.M.porcelain};
  for(const q of InteriorJoinery.parts({...p,joinery:j})){
   let holder=g,pos=q.position;
   if(q.role==='door'&&q.openAngle){holder=new T.Group();const x=pos[0]+(q.hinge==='left'?-1:1)*q.size[0]/2;holder.position.set(x,pos[1],pos[2]);holder.rotation.y=T.MathUtils.degToRad(q.openAngle);g.add(holder);pos=[pos[0]-x,0,0];}
   const mesh=C.box(holder,...q.size,...pos,materials[q.material]||C.M.oak,0,q.name);mesh.userData.joineryRole=q.role;mesh.userData.partName=q.name;
  }
  for(const hole of j.holes||[]){if(hole.kind==='hob')C.box(g,hole.width,.012,hole.depth,hole.x,p.size[1]-.006,hole.z,C.M.black,0,'灶具占位面板');}
  g.position.fromArray(p.position);g.rotation.set(T.MathUtils.degToRad(p.rotationX||0),T.MathUtils.degToRad(p.rotationY||0),T.MathUtils.degToRad(p.rotationZ||0));
  g.userData={sourceId:p.id,roomId:p.roomId,componentId:meta.id,category:meta.category,parametricJoinery:true,semantic:p.name||meta.name};if(j.kind==='ceiling'){g.userData.surfaceType='ceiling';g.userData.ceilingAssembly=true;}C.assets.push(g);return g;
 }};
})(window.CREAM,window.THREE);
