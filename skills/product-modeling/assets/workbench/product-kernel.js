/* Product definition evaluator. Shared verbatim by Node and the browser; no eval. */
(function(root){'use strict';
const own=(o,k)=>Object.prototype.hasOwnProperty.call(o,k);
function finite(v,what){if(typeof v!=='number'||!Number.isFinite(v))throw Error(what+'必须为有限数值');return v;}
function expr(e,env){
 if(typeof e==='number')return finite(e,'表达式');
 if(!Array.isArray(e)||!e.length)throw Error('非法表达式');
 const [op,...args]=e;if(op==='ref'){if(args.length!==1||!own(env,args[0]))throw Error('未定义参数：'+args[0]);return finite(env[args[0]],args[0]);}
 const a=args.map(x=>expr(x,env));let v;
 if(op==='+')v=a.reduce((s,x)=>s+x,0);else if(op==='*')v=a.reduce((s,x)=>s*x,1);
 else if(op==='-'&&a.length===2)v=a[0]-a[1];else if(op==='/'&&a.length===2&&a[1]!==0)v=a[0]/a[1];
 else if(op==='min'&&a.length)v=Math.min(...a);else if(op==='max'&&a.length)v=Math.max(...a);
 else throw Error('不支持的运算：'+op);return finite(v,'计算结果');
}
function values(spec,patch={}){
 if(!spec||spec.format!=='product-modeling'||spec.schemaVersion!==1)throw Error('不是 product-modeling / schemaVersion 1 产品');
 if(!/^[a-z0-9][a-z0-9_-]*$/i.test(spec.id||''))throw Error('产品ID不合法');
 if(!['parametric','mesh'].includes(spec.mode))throw Error('未知产品模式');
 const defs=spec.parameters||{}, input={...(spec.values||{}),...patch}, out={};
 for(const k of Object.keys(input))if(!own(defs,k))throw Error('未知参数：'+k);
 for(const [k,d] of Object.entries(defs)){
  const v=own(input,k)?input[k]:d.default;
  if(d.type==='number'){finite(v,k);if(v<d.min||v>d.max)throw Error(k+'超出允许范围');}
  else if(d.type==='color'){if(typeof v!=='string'||!/^#[0-9a-f]{6}$/i.test(v))throw Error(k+'不是HEX颜色');}
  else if(d.type==='enum'){if(!d.options?.some(o=>(typeof o==='string'?o:o.value)===v))throw Error(k+'不是已定义款式');}
  else throw Error('未知参数类型：'+d.type);out[k]=v;
 }
 for(const [id,e]of Object.entries(spec.edits||{})){
  if(!e||typeof e!=='object')throw Error('非法部件编辑：'+id);
  if(e.offset_mm&&(!Array.isArray(e.offset_mm)||e.offset_mm.length!==3||e.offset_mm.some(n=>typeof n!=='number'||!Number.isFinite(n)||Math.abs(n)>10000)))throw Error('非法位移：'+id);
  if(e.color&&!/^#[0-9a-f]{6}$/i.test(e.color))throw Error('非法颜色：'+id);
  if(e.roughness!==undefined&&(typeof e.roughness!=='number'||!Number.isFinite(e.roughness)||e.roughness<0||e.roughness>1))throw Error('非法粗糙度：'+id);
 }
 return out;
}
function solve(spec,patch={}){
 const v=values(spec,patch), env={...v};
 for(const d of spec.derived||[]){if(own(env,d.id))throw Error('重复计算参数：'+d.id);env[d.id]=expr(d.expr,env);}
 const mat=spec.materials||{}, ids=new Set(), assemblies=new Map((spec.assemblies||[]).map(a=>[a.id,a]));
 if(assemblies.size!==(spec.assemblies||[]).length)throw Error('重复装配ID');
 for(const a of assemblies.values()){const seen=new Set([a.id]);let p=a.parent;while(p){if(!assemblies.has(p)||seen.has(p))throw Error('装配树引用缺失或循环');seen.add(p);p=assemblies.get(p).parent;}}
 const parts=[];
 for(const p of spec.parts||[]){
  if(!p.id||ids.has(p.id))throw Error('重复或空零件ID');ids.add(p.id);
  if(!assemblies.has(p.assembly))throw Error(p.id+'的装配组不存在');
  if(p.variants&&!p.variants.includes(v.variant))continue;
  const q=JSON.parse(JSON.stringify(p));
  if(spec.mode==='parametric'){
   if(!mat[p.material])throw Error('材质不存在：'+p.material);
   if(!['box','cylinder','sphere'].includes(p.primitive))throw Error('不支持的几何类型：'+p.primitive);
   q.size_mm=p.size.map(e=>expr(e,env));q.position_mm=p.position.map(e=>expr(e,env));
   if(q.size_mm.length!==3||q.position_mm.length!==3||q.size_mm.some(n=>n<=0))throw Error('非法零件尺寸：'+p.id);
  }
  parts.push(q);
 }
 if(!parts.length&&spec.mode==='parametric')throw Error('产品没有可见零件');
 return {id:spec.id,name:spec.name,revision:spec.revision,mode:spec.mode,values:v,derived:env,parts,assemblies:[...assemblies.values()],materials:mat};
}
const api={expr,values,solve};root.ProductKernel=api;if(typeof module!=='undefined')module.exports=api;
})(typeof globalThis!=='undefined'?globalThis:this);
