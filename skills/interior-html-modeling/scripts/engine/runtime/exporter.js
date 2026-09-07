

/* Local glTF 2.0 / GLB exporter for the static parametric scene.
   Covers standard PBR materials, normal/color textures, instancing, names and transforms.
   No network calls. Display clipping, environment, lights and contact-shadow cards are excluded. */
(function(C,T){
'use strict';
C.exportGLB=async function(root){
 const json={asset:{version:'2.0',generator:'Interior Studio — static PBR exporter',copyright:'Procedurally authored scene / Three.js MIT'},scene:0,scenes:[{name:'Interior Studio Model',nodes:[]}],nodes:[],meshes:[],materials:[],textures:[],images:[],samplers:[],accessors:[],bufferViews:[],buffers:[{byteLength:0}],extensionsUsed:[]};
 const chunks=[];let offset=0;const geomMap=new Map(),matMap=new Map(),texMap=new Map(),meshMap=new Map();
 function addBytes(bytes,target){const pad=(4-offset%4)%4;if(pad){chunks.push(new Uint8Array(pad));offset+=pad;}const idx=json.bufferViews.length;json.bufferViews.push({buffer:0,byteOffset:offset,byteLength:bytes.byteLength,...(target?{target}: {})});chunks.push(new Uint8Array(bytes.buffer,bytes.byteOffset,bytes.byteLength));offset+=bytes.byteLength;return idx;}
 function attribute(attr,type,target,position=false){let array;if(attr.isInterleavedBufferAttribute){array=new Float32Array(attr.count*attr.itemSize);for(let i=0;i<attr.count;i++)for(let j=0;j<attr.itemSize;j++)array[i*attr.itemSize+j]=attr.data.array[i*attr.data.stride+attr.offset+j];}else array=attr.array;
  const componentType=array instanceof Float32Array?5126:array instanceof Uint32Array?5125:array instanceof Uint16Array?5123:5121;
  const a={bufferView:addBytes(new Uint8Array(array.buffer,array.byteOffset,array.byteLength),target),componentType,count:attr.count,type};
  if(position){a.min=[Infinity,Infinity,Infinity];a.max=[-Infinity,-Infinity,-Infinity];for(let i=0;i<attr.count;i++)for(let k=0;k<3;k++){a.min[k]=Math.min(a.min[k],array[i*3+k]);a.max[k]=Math.max(a.max[k],array[i*3+k]);}}
  if(attr.normalized)a.normalized=true;json.accessors.push(a);return json.accessors.length-1;
 }
 async function texture(t){if(texMap.has(t.uuid))return texMap.get(t.uuid);const im=t.image;if(!im)return null;
  const can=document.createElement('canvas');can.width=im.width;can.height=im.height;const cx=can.getContext('2d');
  // glTF and CanvasTexture have opposite V conventions; bake the source orientation.
  if(t.flipY){cx.translate(0,can.height);cx.scale(1,-1);}cx.drawImage(im,0,0);
  const blob=await new Promise((resolve,reject)=>can.toBlob(b=>b?resolve(b):reject(new Error('贴图编码失败')),'image/png'));
  const bv=addBytes(new Uint8Array(await blob.arrayBuffer()));const imageIdx=json.images.push({name:t.name||'Procedural PBR texture',bufferView:bv,mimeType:'image/png'})-1;
  const wrap=v=>v===T.RepeatWrapping?10497:v===T.MirroredRepeatWrapping?33648:33071;
  const sampler=json.samplers.push({magFilter:9729,minFilter:9987,wrapS:wrap(t.wrapS),wrapT:wrap(t.wrapT)})-1;
  const idx=json.textures.push({source:imageIdx,sampler})-1;texMap.set(t.uuid,idx);return idx;
 }
 async function texInfo(t){const index=await texture(t);if(index===null)return null;const info={index};if(t.repeat.x!==1||t.repeat.y!==1||t.offset.x!==0||t.offset.y!==0||t.rotation!==0){info.extensions={KHR_texture_transform:{offset:[t.offset.x,t.offset.y],scale:[t.repeat.x,t.repeat.y],rotation:t.rotation}};if(!json.extensionsUsed.includes('KHR_texture_transform'))json.extensionsUsed.push('KHR_texture_transform');}return info;}
 async function material(m){if(matMap.has(m.uuid))return matMap.get(m.uuid);const idx=json.materials.length;matMap.set(m.uuid,idx);const j={name:m.name||'Material',pbrMetallicRoughness:{baseColorFactor:[m.color.r,m.color.g,m.color.b,m.opacity??1],metallicFactor:m.metalness??0,roughnessFactor:m.roughness??1}};json.materials.push(j);
  if(m.map)j.pbrMetallicRoughness.baseColorTexture=await texInfo(m.map);if(m.normalMap){j.normalTexture=await texInfo(m.normalMap);j.normalTexture.scale=m.normalScale?.x??1;}
  if(m.emissive){const e=m.emissive.clone().multiplyScalar(m.emissiveIntensity||0);const max=Math.max(e.r,e.g,e.b);j.emissiveFactor=max>1?[e.r/max,e.g/max,e.b/max]:[e.r,e.g,e.b];if(max>1){j.extensions={KHR_materials_emissive_strength:{emissiveStrength:max}};if(!json.extensionsUsed.includes('KHR_materials_emissive_strength'))json.extensionsUsed.push('KHR_materials_emissive_strength');}}
  if(m.transparent&&m.opacity<1)j.alphaMode='BLEND';if(m.side===T.DoubleSide)j.doubleSided=true;return idx;
 }
 async function mesh(o){const g=o.geometry,m=Array.isArray(o.material)?o.material[0]:o.material,key=g.uuid+'|'+m.uuid;if(meshMap.has(key))return meshMap.get(key);let geo=geomMap.get(g.uuid);
  if(!geo){geo={attributes:{POSITION:attribute(g.attributes.position,'VEC3',34962,true)}};if(g.attributes.normal)geo.attributes.NORMAL=attribute(g.attributes.normal,'VEC3',34962);if(g.attributes.uv)geo.attributes.TEXCOORD_0=attribute(g.attributes.uv,'VEC2',34962);if(g.index)geo.indices=attribute(g.index,'SCALAR',34963);geomMap.set(g.uuid,geo);}
  const index=json.meshes.push({name:o.name,primitives:[{...geo,material:await material(m),mode:4}]})-1;meshMap.set(key,index);return index;
 }
 root.updateMatrixWorld(true);
 async function visit(o){if(o.userData.noExport||o.isLight||o.isCamera)return null;const node={name:o.name||o.type},idx=json.nodes.length;json.nodes.push(node);node.matrix=Array.from(o.matrix.elements);if(o.userData.semantic)node.extras={semantic:o.userData.semantic};
  if(o.isInstancedMesh){const mi=await mesh(o),mx=new T.Matrix4();node.children=[];for(let i=0;i<o.count;i++){o.getMatrixAt(i,mx);const ni=json.nodes.push({name:o.name+' '+String(i+1),mesh:mi,matrix:Array.from(mx.elements)})-1;node.children.push(ni);}}
  else if(o.isMesh)node.mesh=await mesh(o);
  const child=[];for(const ch of o.children){const ci=await visit(ch);if(ci!==null)child.push(ci);}if(child.length)node.children=(node.children||[]).concat(child);return idx;
 }
 const ri=await visit(root);json.scenes[0].nodes.push(ri);
 const pad=(4-offset%4)%4;if(pad){chunks.push(new Uint8Array(pad));offset+=pad;}json.buffers[0].byteLength=offset;
 for(const k of ['textures','images','samplers','extensionsUsed'])if(!json[k].length)delete json[k];
 let jb=new TextEncoder().encode(JSON.stringify(json));const jlen=Math.ceil(jb.length/4)*4,total=12+8+jlen+8+offset;const out=new ArrayBuffer(total),dv=new DataView(out),u=new Uint8Array(out);
 dv.setUint32(0,0x46546c67,true);dv.setUint32(4,2,true);dv.setUint32(8,total,true);dv.setUint32(12,jlen,true);dv.setUint32(16,0x4e4f534a,true);u.fill(32,20,20+jlen);u.set(jb,20);dv.setUint32(20+jlen,offset,true);dv.setUint32(24+jlen,0x004e4942,true);let at=28+jlen;for(const c of chunks){u.set(c,at);at+=c.byteLength;}return out;
};
C.downloadBlob=function(blob,name){const a=document.createElement('a');const url=URL.createObjectURL(blob);a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);};
})(window.CREAM,window.THREE);


