/* Registry-driven style components. Shapes are built once in local coordinates.
   No project room coordinates or camera positions belong here. */
(function(C,T){'use strict';
 const B=C.box,G=C.group,cy=C.cyl,M=C.M;
 const extra={
 washer(p){const g=G(p,'滚筒洗衣机');B(g,.60,.82,.59,0,.43,0,M.cream,.035);B(g,.56,.1,.026,0,.77,.309,M.porcelain,.009);B(g,.19,.044,.008,-.14,.77,.326,M.black,.004);const dial=cy(g,.027,.027,.025,.19,.77,.327,M.bronze,24);dial.rotation.x=Math.PI/2;const drum=cy(g,.205,.205,.037,0,.39,.318,M.black,48);drum.rotation.x=Math.PI/2;C.ring(g,.208,.022,0,.39,.349,M.bronze);const inner=cy(g,.165,.165,.014,0,.39,.345,M.mirror,48);inner.rotation.x=Math.PI/2;B(g,.06,.14,.035,.19,.39,.364,M.cream,.015);for(const x of[-.23,.23])for(const z of[-.22,.22])cy(g,.028,.03,.045,x,.025,z,M.dark,12);return g;},
 windowBench(p){const g=G(p,'飘窗坐台 / 储物 / 软垫');B(g,1.8,.35,.61,0,.195,0,M.oak,.012);for(const x of[-.45,.45]){B(g,.87,.25,.024,x,.21,.316,M.cream,.009);B(g,.13,.012,.022,x,.30,.337,M.bronze,.004);}C.pillow(g,1.78,.095,.60,0,.419,0,M.linen);const pillow=C.pillow(g,.42,.30,.15,-.60,.56,-.16,M.sand,.07);pillow.rotation.x=.13;return g;},
 upperCabinet(p){const g=G(p,'吊柜 / 独立门板');B(g,1.20,.75,.33,0,.395,0,M.oak,.012);for(const x of[-.30,.30])B(g,.582,.716,.025,x,.395,.18,M.cream,.009);B(g,1.11,.012,.021,0,.025,.11,M.led,.003);return g;},
 pendant(p){const g=G(p,'餐桌双灯吊灯');B(g,.48,.036,.10,0,.558,0,M.bronze,.016);for(const x of[-.29,.29]){C.rod(g,[x*.5,.54,0],[x,.26,0],.005,M.bronze);const shade=C.lathe(g,[[0,.13],[.10,.13],[.20,.04],[.22,-.075],[.20,-.09],[0,-.09]],x,.12,0,M.cream,'磨砂灯罩');C.sphere(g,.083,.083,.083,x,.10,0,M.led);}return g;},
 coffee(p){const g=G(p,'双拼茶几');const a=cy(g,.63,.63,.09,0,.385,0,M.travertine,64);a.scale.z=.7;for(const x of[-.32,.32])cy(g,.14,.16,.33,x,.19,0,M.travertine);cy(g,.37,.37,.045,.57,.47,.24,M.oak,48);cy(g,.12,.15,.435,.57,.235,.24,M.oak);C.book(g,.30,.22,.035,-.12,.435,.08,'#a79c83');C.vase(g,.11,.435,-.13,.15,.085);return g;},
 dining(p){const g=G(p,'椭圆餐桌');const top=cy(g,.97,.97,.065,0,.775,0,M.travertine,64);top.scale.x=.51;for(const z of[-.52,.52]){const leg=cy(g,.24,.25,.70,0,.385,z,M.oak,40);leg.scale.x=.82;}for(const z of[-.53,.53]){cy(g,.12,.12,.012,-.05,.819,z,M.porcelain,32);C.rod(g,[.13,.827,z-.09],[.13,.827,z+.09],.005,M.bronze);}return g;},
 sideboard(p){const g=G(p,'餐边柜');B(g,1.94,.78,.43,0,.46,0,M.oak,.035);for(let i=0;i<3;i++){B(g,.63,.66,.025,-.65+i*.65,.475,.231,M.cream,.015);B(g,.12,.012,.022,-.65+i*.65,.62,.258,M.bronze,.005);}B(g,2.01,.04,.48,0,.875,0,M.travertine,.016);return g;},
 tv(p){const g=G(p,'电视/悬浮柜');B(g,3.15,2.60,.095,0,1.32,-.15,M.travertine,.03);B(g,2.94,.235,.41,0,.40,.1,M.oak,.045);for(let i=0;i<4;i++)B(g,.72,.185,.024,-1.105+i*.738,.42,.319,M.cream,.012);B(g,1.93,1.12,.045,-.10,1.52,-.08,M.black,.018);B(g,1.873,1.065,.007,-.10,1.52,-.052,M.screen,.013);C.vase(g,1.12,.53,.10,.21,.07);return g;},
 counter(p){const g=G(p,'地柜');B(g,.68,.78,.60,0,.43,0,M.oak,.012);B(g,.67,.065,.63,0,.867,0,M.travertine,.012);B(g,.64,.10,.53,0,.065,0,M.dark,.004);for(let i=0;i<3;i++){B(g,.65,.23,.032,0,.23+i*.24,.316,M.cream,.008);B(g,.22,.012,.021,0,.295+i*.24,.341,M.bronze,.004);}return g;},
 sink(p){const g=G(p,'水槽地柜');B(g,.96,.79,.60,0,.43,0,M.oak,.012);for(const x of[-.24,.24])B(g,.467,.72,.03,x,.47,.315,M.cream,.01);
  // A genuine countertop hole: four solid strips, not a black decal on a slab.
  for(const x of[-.413,.413])B(g,.17,.05,.65,x,.87,0,M.travertine,.008);for(const z of[-.278,.278])B(g,.68,.05,.094,0,.87,z,M.travertine,.006);
  B(g,.65,.018,.46,0,.68,0,M.black,.018);for(const x of[-.327,.327])B(g,.018,.18,.46,x,.78,0,M.black,.006);for(const z of[-.229,.229])B(g,.65,.18,.018,0,.78,z,M.black,.006);
  C.tube(g,[[.25,.88,-.26],[.25,1.17,-.26],[.17,1.24,-.23],[.09,1.24,-.13],[.09,1.13,-.10]],.014,M.bronze);cy(g,.026,.026,.003,0,.693,0,M.bronze);return g;},
 hob(p){const g=extra.counter(p);B(g,.60,.018,.48,0,.91,0,M.black,.015);for(const x of[-.15,.15]){cy(g,.095,.095,.015,x,.93,0,M.bronze,32);C.ring(g,.074,.006,x,.942,0,M.black,Math.PI/2);}B(g,.58,.38,.02,0,.43,.337,M.black,.012);B(g,.38,.22,.012,0,.43,.352,M.mirror,.006);B(g,.36,.018,.034,0,.66,.368,M.bronze,.005);return g;},
 fridge(p){const g=G(p,'双区冰箱');B(g,.8,2.22,.7,0,1.13,0,M.oak,.017);B(g,.73,1.44,.04,0,1.47,.38,M.cream,.024);B(g,.73,.67,.04,0,.39,.38,M.cream,.021);B(g,.018,.47,.04,-.23,1.29,.421,M.bronze,.006);B(g,.23,.015,.04,0,.64,.421,M.bronze,.006);return g;},
 vanity(p){const g=G(p,'浴室柜');B(g,.8,.46,.49,0,.555,0,M.oak,.03);for(let i=0;i<23;i++)B(g,.013,.4,.016,-.365+i*.033,.56,.25,M.oak,.005);B(g,.84,.045,.53,0,.819,0,M.travertine,.013);
  const bowl=C.lathe(g,[[0,0],[.135,0],[.171,.035],[.19,.116],[.182,.13],[.165,.126],[.149,.047],[0,.04]],0,.845,0,M.porcelain,'空心陶盆');bowl.scale.x=1.23;C.tube(g,[[.27,.84,-.13],[.27,1.08,-.13],[.24,1.12,-.1],[.18,1.12,-.1],[.18,1.065,-.1]],.011,M.bronze);B(g,.70,1.04,.025,0,1.63,-.27,M.bronze,.012);B(g,.66,1,.013,0,1.63,-.25,M.mirror,.006);return g;},
 toilet(p){const g=G(p,'坐便器');const body=C.lathe(g,[[0,0],[.13,0],[.14,.09],[.17,.23],[.21,.34],[.205,.39],[.17,.41],[.11,.30],[0,.26]],0,.015,.09,M.porcelain);body.scale.z=1.47;B(g,.36,.49,.19,0,.315,-.22,M.porcelain,.075);const seat=C.ring(g,.183,.023,0,.442,.09,M.porcelain,Math.PI/2);seat.scale.y=1.42;B(g,.34,.043,.50,0,.481,.064,M.cream,.021);return g;},
 shower(p){const g=G(p,'淋浴/玻璃');B(g,1.05,.045,.86,0,.025,0,M.travertine,.015);B(g,.35,.008,.05,.19,.052,0,M.bronze,.002);B(g,.014,2.08,.84,-.51,1.09,0,M.glass);B(g,.85,2.08,.014,.075,1.09,.415,M.glass);for(const x of[-.51,.50])B(g,.024,2.18,.028,x,1.13,.42,M.bronze,.004);C.rod(g,[.25,.92,-.40],[.25,2.05,-.40],.013,M.bronze);C.tube(g,[[.25,2.05,-.40],[.25,2.17,-.38],[.25,2.17,-.11]],.014,M.bronze);cy(g,.115,.115,.022,.25,2.155,-.1,M.bronze,40);C.tube(g,[[.25,1.02,-.37],[.44,.48,-.30],[.10,.48,-.32],[.04,1.23,-.34]],.009,M.bronze);return g;},
 floorLamp(p){const g=G(p,'落地灯');cy(g,.22,.22,.035,0,.022,0,M.travertine);C.tube(g,[[0,.04,0],[0,1.44,0],[-.09,1.77,-.04],[-.50,1.92,-.09],[-.79,1.76,-.12]],.012,M.bronze);C.lathe(g,[[0,.14],[.09,.13],[.20,-.06],[.20,-.075]],-.79,1.73,-.12,M.cream);return g;}
 };
 // Tight vertex bounds. Transforming child AABBs before batching changes their
 // over-estimation; the canonical component size must not depend on batching order.
 C.localBounds=function(root,relativeTo=null){root.updateWorldMatrix(true,true);const box=new T.Box3(),point=new T.Vector3(),matrix=new T.Matrix4(),instance=new T.Matrix4(),inverse=relativeTo?relativeTo.matrixWorld.clone().invert():null;
  root.traverse(o=>{if(!o.isMesh||o.userData.noExport)return;const positions=o.geometry.attributes.position,count=o.isInstancedMesh?o.count:1;
   for(let k=0;k<count;k++){matrix.copy(o.matrixWorld);if(o.isInstancedMesh){o.getMatrixAt(k,instance);matrix.multiply(instance);}if(inverse)matrix.premultiply(inverse);
    for(let i=0;i<positions.count;i++){point.fromBufferAttribute(positions,i).applyMatrix4(matrix);box.expandByPoint(point);}}
  });return box;};
 C.instantiate=function(parent,spec,registry){const meta=registry.components.find(x=>x.id===spec.componentId);if(!meta)throw Error('未知 componentId: '+spec.componentId);
  const saved=C.assets;C.assets=[];const holder=new T.Group();let built;
  built=C.buildStyled(meta.builder,holder,meta);
  if(!built)switch(meta.builder){
  case 'sofa':built=C.sofa(holder,0,0);built.rotation.y=Math.PI;break;
  case 'chair':built=C.chair(holder,0,0,Math.PI);break;
  case 'armchair':built=C.armchair(holder,0,0,Math.PI);break;
  case 'bed':built=C.bed(holder,0,0,1.8);break;
  case 'wardrobe':built=C.wardrobe(holder,1.8,0,0);break;
  case 'desk':built=C.desk(holder,0,0,1.5);break;
  case 'shelf':built=C.shelf(holder,0,0,1.5);break;
  case 'sideTable':built=C.sideTable(holder,0,0);break;
  case 'rug':built=C.rug(holder,3.5,2.8,0,0);break;
  case 'plant':built=C.plant(holder,0,0,1.9);break;
  case 'tableLamp':built=C.lamp(holder,0,0,0);break;
  case 'curtain':built=C.curtain(holder,2.9,2.65,0,0,0);break;
  case 'art':built=C.frame(holder,.8,1.0,0,.5,0);break;
  default:if(!extra[meta.builder])throw Error('组件构造器不存在: '+meta.builder);built=extra[meta.builder](holder);
  }
  C.assets=saved;const b=C.localBounds(holder),dim=b.getSize(new T.Vector3()),center=b.getCenter(new T.Vector3());
  // Every reusable component follows the same footprint-centre / floor origin contract.
  const content=new T.Group();content.position.set(-center.x,-b.min.y,-center.z);while(holder.children.length)content.add(holder.children[0]);holder.add(content);
  holder.scale.set(spec.size[0]/dim.x,spec.size[1]/dim.y,spec.size[2]/dim.z);holder.position.fromArray(spec.position);holder.rotation.y=T.MathUtils.degToRad(spec.rotationY);
  holder.name=spec.name||meta.name;holder.userData={semantic:holder.name,sourceId:spec.id,roomId:spec.roomId,componentId:meta.id,category:meta.category,styleId:C.activeStyle.id,styleVariant:built?.userData.styleVariant||('material:'+C.activeStyle.id)};parent.add(holder);C.assets.push(holder);return holder;
 };
})(window.CREAM,window.THREE);
