import * as THREE from 'three';
// Defaults make a provisional camera; they are not evidence of a fitted viewpoint.
export const cameraDefaults=Object.freeze({az:-30,el:15,distance:3,targetY:.5,fov:40,shiftX:0,shiftY:0});
export function cameraFor(input={},w,h){
 if(!Number.isFinite(w)||!Number.isFinite(h)||w<=0||h<=0)throw Error('参考图宽高必须为正数');
 const p={...cameraDefaults,...input};
 for(const k of Object.keys(cameraDefaults))if(!Number.isFinite(p[k]))throw Error('相机参数必须为有限数字：'+k);
 if(p.distance<=0||p.fov<=0||p.fov>=179)throw Error('相机距离或视角超出有效范围');
 const near=Math.max(.00001,p.distance/10000),far=Math.max(100,p.distance*100);
 const c=new THREE.PerspectiveCamera(p.fov,w/h,near,far),a=p.az*Math.PI/180,e=p.el*Math.PI/180;
 c.position.set(p.distance*Math.sin(a)*Math.cos(e),p.targetY+p.distance*Math.sin(e),p.distance*Math.cos(a)*Math.cos(e));
 c.lookAt(0,p.targetY,0);c.setViewOffset(w,h,-p.shiftX*w,-p.shiftY*h,w,h);c.updateMatrixWorld();return c;
}
export function pixel(point,c,w,h){const q=new THREE.Vector3(...point).project(c);return [(q.x+1)*w/2,(1-q.y)*h/2];}
export function pointReport(anchors,observations,c,w,h){return observations.map(o=>{if(!anchors[o.id])throw Error('Unbound '+o.id);let predicted=pixel(anchors[o.id],c,w,h);return {...o,xyz:anchors[o.id],predicted,errorPx:Math.hypot(predicted[0]-o.pixel[0],predicted[1]-o.pixel[1])};});}
export function pointLoss(report,w,h){let sum=0,weights=0;for(const a of report){if(a.role!=='fit')continue;const r=a.errorPx/Math.hypot(w,h),delta=.02;sum+=(a.weight??1)*(r<delta?r*r:2*delta*r-delta*delta);weights+=a.weight??1;}return sum/Math.max(1,weights);}
export function coordinateSolve(start,bounds,objective,{rounds=10,step=.12}={}){
 let p=checkedStart(start,bounds),best=objective(p),trace=[{round:0,loss:best}],evaluations=1;
 for(let round=0;round<rounds;round++){let changed=false;for(const [k,[lo,hi]] of Object.entries(bounds)){
 const d=(hi-lo)*step;let winner=p;for(const direction of [-1,1]){const q={...p,[k]:Math.max(lo,Math.min(hi,p[k]+direction*d))};const loss=objective(q);evaluations++;if(Number.isFinite(loss)&&loss<best){best=loss;winner=q;changed=true;}}p=winner;
 }trace.push({round:round+1,loss:best});if(!changed)step*=.5;}
 return {parameters:p,loss:best,trace,evaluations};
}
export function contourMetrics(rendered,target,w,h){if(!rendered||!target||!Number.isInteger(w)||!Number.isInteger(h)||w<=0||h<=0||rendered.length!==w*h||target.length!==w*h)throw Error('轮廓需要同尺寸二值掩码；未标注不能当零误差');let intersection=0,union=0;const edges=m=>{let a=[];for(let y=0;y<h;y++)for(let x=0;x<w;x++){const i=y*w+x;if(m[i]&&(x===0||y===0||x===w-1||y===h-1||!m[i-1]||!m[i+1]||!m[i-w]||!m[i+w]))a.push([x,y]);}return a;};
 for(let i=0;i<target.length;i++){if(rendered[i]&&target[i])intersection++;if(rendered[i]||target[i])union++;}
 const a=edges(rendered),b=edges(target);const distance=(u,v)=>{if(!u.length||!v.length)return Math.hypot(w,h);let sum=0;for(let i=0;i<u.length;i+=3){let d=Infinity;for(let j=0;j<v.length;j+=3)d=Math.min(d,(u[i][0]-v[j][0])**2+(u[i][1]-v[j][1])**2);sum+=Math.sqrt(d);}return sum/Math.ceil(u.length/3);};
 return {iou:intersection/Math.max(1,union),boundaryDistancePx:(distance(a,b)+distance(b,a))/2};
}
export function simplexSolve(start,bounds,objective,{iterations=900,tolerance=1e-10}={}){
 start=checkedStart(start,bounds);const keys=Object.keys(bounds),n=keys.length,encode=p=>keys.map(k=>(p[k]-bounds[k][0])/(bounds[k][1]-bounds[k][0]));
 const decode=x=>Object.fromEntries([...Object.entries(start),...keys.map((k,i)=>[k,bounds[k][0]+Math.max(0,Math.min(1,x[i]))*(bounds[k][1]-bounds[k][0])])]);
 let evaluations=0;const evaluate=x=>{x=x.map(v=>Math.max(0,Math.min(1,v)));evaluations++;const value=objective(decode(x));return {x,value:Number.isFinite(value)?value:Infinity};};
 if(n===0)return {parameters:start,loss:objective(start),evaluations:1,trace:[]};let x=encode(start),s=[evaluate(x),...x.map((v,i)=>evaluate(x.map((q,j)=>q+(i===j?.035:0))))],trace=[];
 for(let t=0;t<iterations;t++){s.sort((a,b)=>a.value-b.value);if(t%50===0)trace.push({iteration:t,loss:s[0].value});if(t>100&&Math.abs(s[n].value-s[0].value)<tolerance)break;
 let c=Array(n).fill(0);for(let i=0;i<n;i++)for(let j=0;j<n;j++)c[j]+=s[i].x[j]/n;const trial=f=>evaluate(c.map((v,j)=>v+f*(v-s[n].x[j])));let r=trial(1);
 if(r.value<s[0].value){let e=trial(2);s[n]=e.value<r.value?e:r;}else if(r.value<s[n-1].value)s[n]=r;else{let q=trial(r.value<s[n].value?.5:-.5);if(q.value<Math.min(r.value,s[n].value))s[n]=q;else for(let i=1;i<=n;i++)s[i]=evaluate(s[i].x.map((v,j)=>(v+s[0].x[j])/2));}
 }s.sort((a,b)=>a.value-b.value);return {parameters:decode(s[0].x),loss:s[0].value,evaluations,trace};
}

function checkedStart(start,bounds){const p={...start};for(const [k,pair] of Object.entries(bounds)){const [lo,hi]=pair;if(!Number.isFinite(lo)||!Number.isFinite(hi)||hi<=lo||!Number.isFinite(p[k]))throw Error('非法求解初值/边界：'+k);p[k]=Math.max(lo,Math.min(hi,p[k]));}return p;}
