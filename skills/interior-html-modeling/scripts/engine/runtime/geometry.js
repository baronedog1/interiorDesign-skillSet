

/* Geometry toolkit. Units: metres. Y up. Parametric geometry, never image billboards. */
(function(C,T){
'use strict';
const cache=new Map();
function roundedGeo(w,h,d,r){
 const key=[w,h,d,r].join('/');if(cache.has(key))return cache.get(key);
 r=Math.min(r,w*.48,h*.48,d*.48);
 const g=new T.BoxGeometry(w,h,d,6,6,6),p=g.attributes.position,n=g.attributes.normal;
 const dims=[w,h,d],v=new T.Vector3(),inner=new T.Vector3(),norm=new T.Vector3();
 for(let i=0;i<p.count;i++){
  let a=[p.getX(i),p.getY(i),p.getZ(i)].map((q,j)=>{const half=dims[j]/2,idx=Math.round((q/dims[j]+.5)*6);return [-half,-half+r*.293,-half+r,0,half-r,half-r*.293,half][idx];});
  v.set(...a);inner.set(T.MathUtils.clamp(v.x,-w/2+r,w/2-r),T.MathUtils.clamp(v.y,-h/2+r,h/2-r),T.MathUtils.clamp(v.z,-d/2+r,d/2-r));norm.subVectors(v,inner).normalize();v.copy(inner).addScaledVector(norm,r);p.setXYZ(i,v.x,v.y,v.z);n.setXYZ(i,norm.x,norm.y,norm.z);
 }
 g.computeBoundingSphere();cache.set(key,g);return g;
}
C.mesh=function(parent,geometry,material,name,x=0,y=0,z=0){const m=new T.Mesh(geometry,material);m.position.set(x,y,z);m.castShadow=m.receiveShadow=true;m.name=name||material.name;parent.add(m);return m;};
C.box=function(parent,w,h,d,x,y,z,mat=C.M.cream,r=0,name=''){return C.mesh(parent,r>0?roundedGeo(w,h,d,r):new T.BoxGeometry(w,h,d),mat,name,x,y,z);};
C.cyl=function(parent,rt,rb,h,x,y,z,mat=C.M.oak,segments=32,name=''){return C.mesh(parent,new T.CylinderGeometry(rt,rb,h,segments,1,false),mat,name,x,y,z);};
C.sphere=function(parent,rx,ry,rz,x,y,z,mat=C.M.cream,name=''){const m=C.mesh(parent,new T.SphereGeometry(1,24,16),mat,name,x,y,z);m.scale.set(rx,ry,rz);return m;};
C.group=function(parent,name,x=0,y=0,z=0,rot=0){const g=new T.Group();g.name=name;g.position.set(x,y,z);g.rotation.y=rot;parent.add(g);return g;};
C.tube=function(parent,pts,r,mat=C.M.bronze,closed=false,name=''){const curve=new T.CatmullRomCurve3(pts.map(p=>p.isVector3?p:new T.Vector3(...p)),closed);return C.mesh(parent,new T.TubeGeometry(curve,Math.max(16,pts.length*6),r,7,closed),mat,name);};
C.rod=function(parent,a,b,r,mat=C.M.bronze,name=''){const va=new T.Vector3(...a),vb=new T.Vector3(...b),m=C.cyl(parent,r,r,va.distanceTo(vb),0,0,0,mat,12,name);m.position.copy(va).add(vb).multiplyScalar(.5);m.quaternion.setFromUnitVectors(new T.Vector3(0,1,0),vb.sub(va).normalize());return m;};
C.lathe=function(parent,profile,x,y,z,mat=C.M.porcelain,name=''){return C.mesh(parent,new T.LatheGeometry(profile.map(p=>new T.Vector2(...p)),40),mat,name,x,y,z);};
C.ring=function(parent,r,t,x,y,z,mat=C.M.bronze,rx=0){const m=C.mesh(parent,new T.TorusGeometry(r,t,8,48),mat,'环形细部',x,y,z);m.rotation.x=rx;return m;};
C.pillow=function(parent,w,h,d,x,y,z,mat=C.M.linen,rot=0){
 const g=new T.SphereGeometry(1,32,20),p=g.attributes.position;
 const power=(v,k)=>Math.sign(v)*Math.pow(Math.abs(v),k);
 for(let i=0;i<p.count;i++){const a=p.getX(i),b=p.getY(i),c=p.getZ(i);p.setXYZ(i,power(a,.48)*w/2,power(b,.6)*h/2,power(c,.55)*d/2);}
 g.computeVertexNormals();const m=C.mesh(parent,g,mat,'软包织物 / 鼓包枕芯',x,y,z);m.rotation.z=rot;return m;
};
C.contact=function(parent,w,d,x,z,y=.006){const m=new T.Mesh(new T.PlaneGeometry(w,d),new T.MeshBasicMaterial({name:'柔和接触阴影',map:C.contactTexture,transparent:true,depthWrite:false,opacity:.62}));m.rotation.x=-Math.PI/2;m.position.set(x,y,z);m.userData.noExport=true;parent.add(m);return m;};
C.frame=function(parent,w,h,x,y,z,style=0,rot=0){const g=C.group(parent,'装裱原创艺术画',x,y,z,rot);C.box(g,w+.07,h+.07,.04,0,0,0,C.M.oak,.006);C.box(g,w,h,.045,0,0,.011,C.M.white);C.box(g,w*.86,h*.85,.009,0,0,.039,C.makeArt(style));return g;};
C.book=function(parent,w,d,h,x,y,z,col='#9a8b75',rot=0){const g=C.group(parent,'书册 / 独立封面与书芯',x,y,z,rot);const m=C.mat('书封',col,.9);C.box(g,w,h*.78,d,0,h/2,0,C.M.white,.003);C.box(g,w+.008,.006,d+.006,0,.003,0,m);C.box(g,w+.008,.006,d+.006,0,h-.003,0,m);C.box(g,.007,h,d+.006,-w/2,h/2,0,m);return g;};
C.geometryCache=cache;
})(window.CREAM,window.THREE);


