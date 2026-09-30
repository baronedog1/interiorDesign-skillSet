import * as T from 'three';
const texture=async url=>{let t=await new T.TextureLoader().loadAsync(url);t.colorSpace=T.SRGBColorSpace;t.anisotropy=4;return t;};
export async function finishMaterials({model,scene,renderer,referenceCamera,reference,referenceSize,finish={}}){
 const [W,H]=referenceSize,images={};for(const [name,url] of Object.entries(finish.textures||{})){images[name]=await texture(url);images[name].wrapS=images[name].wrapT=T.RepeatWrapping;}
 const photo=await texture(reference);
 const categories=[...new Set([...Object.keys(finish.materials||{}),...(finish.regions||[]).map(r=>r.category)])];if(categories.length>254)throw Error('材质区域类别过多');const categoryCode=new Map(categories.map((c,i)=>[c,i+1]));const maskCanvas=document.createElement('canvas');maskCanvas.width=W;maskCanvas.height=H;const ctx=maskCanvas.getContext('2d');ctx.fillStyle='black';ctx.fillRect(0,0,W,H);
 for(const item of finish.regions||[]){ctx.fillStyle=`rgb(${categoryCode.get(item.category)},0,0)`;ctx.beginPath();item.polygon.forEach((p,i)=>i?ctx.lineTo(...p):ctx.moveTo(...p));ctx.closePath();ctx.fill();}
 const mask=new T.CanvasTexture(maskCanvas);mask.minFilter=T.NearestFilter;mask.magFilter=T.NearestFilter;mask.colorSpace=T.NoColorSpace;
 const size=Math.min(1,1536/W);const refRT=new T.WebGLRenderTarget(Math.round(W*size),Math.round(H*size));refRT.depthTexture=new T.DepthTexture(refRT.width,refRT.height,T.UnsignedIntType);
 const oldTarget=renderer.getRenderTarget(),oldOverride=scene.overrideMaterial;scene.overrideMaterial=new T.MeshDepthMaterial({side:T.DoubleSide});renderer.setRenderTarget(refRT);renderer.render(scene,referenceCamera);renderer.setRenderTarget(oldTarget);scene.overrideMaterial.dispose();scene.overrideMaterial=oldOverride;
 const refMatrix=new T.Matrix4().multiplyMatrices(referenceCamera.projectionMatrix,referenceCamera.matrixWorldInverse);
 for(const mesh of model.parts){
  const category=mesh.userData.category||'fabric',spec=finish.materials?.[category]||{};
  const map=images[spec.texture];const material=new T.MeshStandardMaterial({color:spec.color||'#ffffff',map:map||null,roughness:spec.roughness??.8,metalness:0,side:T.DoubleSide});
  // Local UVs are bound to the surface, never the viewing camera. Inferred sides use these textures.
  if(map){const pos=mesh.geometry.attributes.position,uv=[];const scale=spec.scale??1;
   for(let i=0;i<pos.count;i++){let x=pos.getX(i),y=pos.getY(i),z=pos.getZ(i);if(category==='wood'){
    const axis=mesh.userData.grainAxis||'y';uv.push((axis==='x'?y:axis==='z'?x:x+z)*scale,(axis==='x'?x:axis==='z'?z:y)*scale);
   }else if(category==='linen'){uv.push(x*scale*2,y*scale*2);}else{const old=mesh.geometry.attributes.uv;uv.push((old?old.getX(i):x)*scale,(old?old.getY(i):y)*scale);}}
   mesh.geometry.setAttribute('uv',new T.Float32BufferAttribute(uv,2));
  }
  if(spec.projectReference){
   material.onBeforeCompile=function(shader){
    Object.assign(shader.uniforms,{refTint:{value:this.color},refPhoto:{value:photo},refMask:{value:mask},refDepth:{value:refRT.depthTexture},refMatrix:{value:refMatrix},refEye:{value:referenceCamera.position.clone()},refCategory:{value:(categoryCode.get(category)??0)/255},refGain:{value:spec.photoGain??1},refStrength:{value:spec.photoStrength??1}});
    shader.vertexShader='uniform mat4 refMatrix; varying vec4 refClip; varying vec3 refWorld; varying vec3 refNormal;\n'+shader.vertexShader;
    shader.vertexShader=shader.vertexShader.replace('#include <project_vertex>','#include <project_vertex>\nrefWorld=(modelMatrix*vec4(transformed,1.0)).xyz;refClip=refMatrix*vec4(refWorld,1.0);refNormal=normalize(mat3(modelMatrix)*objectNormal);');
    shader.fragmentShader='uniform vec3 refTint;uniform sampler2D refPhoto;uniform sampler2D refMask;uniform sampler2D refDepth;uniform vec3 refEye;uniform float refCategory;uniform float refGain;uniform float refStrength;varying vec4 refClip;varying vec3 refWorld;varying vec3 refNormal;\n'+shader.fragmentShader;
    shader.fragmentShader=shader.fragmentShader.replace('#include <map_fragment>',`#include <map_fragment>
     vec3 rn=refClip.xyz/refClip.w;vec2 ru=rn.xy*.5+.5;
     float inside=step(0.0,ru.x)*step(ru.x,1.0)*step(0.0,ru.y)*step(ru.y,1.0);
     float surfaceDepth=rn.z*.5+.5;float depth=texture2D(refDepth,ru).r;
     float visibility=1.0-smoothstep(.000004,.000022,abs(surfaceDepth-depth));
     float categoryMatch=step(.5/255.0,refCategory)*(1.0-step(.5/255.0,abs(texture2D(refMask,ru).r-refCategory)));
     float facing=smoothstep(.005,.035,abs(dot(normalize(refNormal),normalize(refEye-refWorld))));
     vec3 sourceColor=texture2D(refPhoto,ru).rgb;
     float nonBackground=1.0-smoothstep(.83,.96,min(sourceColor.r,min(sourceColor.g,sourceColor.b)));
     float blendWeight=step(0.0,refClip.w)*inside*visibility*categoryMatch*facing*nonBackground*refStrength;
     diffuseColor.rgb=mix(diffuseColor.rgb,sourceColor*refGain*refTint,blendWeight);
    `);
   };
   material.customProgramCacheKey=()=>`surface-reference-${category}`;
  }
  mesh.material?.dispose();mesh.material=material;mesh.castShadow=true;mesh.receiveShadow=true;
 }
 return {dispose(){refRT.dispose();photo.dispose();mask.dispose();for(const t of Object.values(images))t.dispose();},referenceDepth:refRT,textures:images,method:'fixed reference-camera surface projection with depth/category/normal gating; inferred surfaces use local UV textures',limitations:'source photo contains residual lighting; not measured intrinsic albedo'};
}
