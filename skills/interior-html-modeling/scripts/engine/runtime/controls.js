
/* Camera math only. Pointer ownership belongs to Interaction in app.js.
   Selecting an object never changes target. Orbit and look are intentionally distinct. */
(function(C,T){'use strict';
 C.CameraControls=class{
  constructor(camera,el){this.camera=camera;this.el=el;this.target=new T.Vector3();this.mode='orbit';this.twoPoint=false;this.minDistance=.25;this.maxDistance=65;}
  lookAt(){this.camera.lookAt(this.target);this.camera.updateMatrixWorld(true);}
  rotate(dx,dy){const c=this.camera;if(c.isOrthographicCamera){this.pan(dx,dy);return;}
   if(this.mode==='look'){
    const v=this.target.clone().sub(c.position),d=Math.max(.25,v.length()),yaw=Math.atan2(v.x,v.z)-dx*.0045,pitch=this.twoPoint?0:T.MathUtils.clamp(Math.asin(T.MathUtils.clamp(v.y/d,-1,1))+dy*.0045,-1.45,1.45);
    this.target.copy(c.position).add(new T.Vector3(Math.sin(yaw)*Math.cos(pitch),Math.sin(pitch),Math.cos(yaw)*Math.cos(pitch)).multiplyScalar(d));
   }else{
    const s=new T.Spherical().setFromVector3(c.position.clone().sub(this.target));s.radius=T.MathUtils.clamp(s.radius,this.minDistance,this.maxDistance);s.theta-=dx*.005;s.phi=this.twoPoint?Math.PI/2:T.MathUtils.clamp(s.phi-dy*.005,.055,Math.PI*.495);
    c.position.copy(this.target).add(new T.Vector3().setFromSpherical(s));
   }this.lookAt();
  }
  pan(dx,dy){const c=this.camera;c.updateMatrixWorld(true);const d=Math.max(.25,c.position.distanceTo(this.target)),h=Math.max(1,this.el.clientHeight),s=c.isOrthographicCamera?(c.top-c.bottom)/c.zoom/h:2*d*Math.tan(T.MathUtils.degToRad(c.fov/2))/h;
   const right=new T.Vector3().setFromMatrixColumn(c.matrixWorld,0),up=new T.Vector3().setFromMatrixColumn(c.matrixWorld,1),move=right.multiplyScalar(-dx*s).add(up.multiplyScalar(dy*s));c.position.add(move);this.target.add(move);this.lookAt();}
  zoom(delta){const c=this.camera;if(c.isOrthographicCamera){c.zoom=T.MathUtils.clamp(c.zoom*Math.exp(-delta),.3,10);c.updateProjectionMatrix();}
   else if(this.mode==='look'){const v=this.target.clone().sub(c.position).normalize().multiplyScalar(-delta*1.8);c.position.add(v);this.target.add(v);}
   else{const v=c.position.clone().sub(this.target);v.setLength(T.MathUtils.clamp(v.length()*Math.exp(delta),this.minDistance,this.maxDistance));c.position.copy(this.target).add(v);}this.lookAt();}
  walk(forward,right,vertical){const c=this.camera,v=this.target.clone().sub(c.position);v.y=0;v.normalize();const r=new T.Vector3().crossVectors(v,new T.Vector3(0,1,0));const m=v.multiplyScalar(forward).addScaledVector(r,right);m.y+=vertical;c.position.add(m);this.target.add(m);this.lookAt();}
 };
})(window.CREAM,window.THREE);

