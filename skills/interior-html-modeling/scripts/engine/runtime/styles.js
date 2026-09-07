/* Executable style recipes. The editor UI is neutral; style changes materials AND
 * selected family geometry. No duplicate editor template per style. */
(function(C,T){'use strict';
 const original={};for(const[k,m]of Object.entries(C.M))original[k]={color:m.color?.getHex(),roughness:m.roughness,metalness:m.metalness,map:m.map,normalMap:m.normalMap,normalScale:m.normalScale?.clone()};
 const forms={sofa:['cloud','linear','timber','low','lattice'],bed:['soft','panel','timber','platform','lattice'],chair:['rounded','linear','timber','organic','lattice'],tables:['oval','rectilinear','tapered','organic','trestle'],cabinet:['fluted','flat','timber','block','lattice'],pendant:['dome','linear','sputnik','paper','lantern'],art:['arches','geometry','earth','ink']};
 const col=x=>typeof x==='string'&&/^#[0-9a-f]{6}$/i.test(x);
 C.validateStyle=function(s){if(!s||!/^[-a-z0-9]{1,50}$/.test(s.id)||typeof s.name!=='string'||!s.name.length||s.name.length>60||typeof s.englishName!=='string'||typeof s.renderBrief!=='string'||!s.materialRecipes||typeof s.materialRecipes!=='object')throw Error('风格需要合法 id 和名称');for(const k of Object.keys(forms))if(!forms[k].includes(s.forms?.[k]))throw Error('不支持的造型 '+k);if(!col(s.theme?.accent)||(s.theme.background!=null&&!col(s.theme.background))||(s.theme.text!=null&&!col(s.theme.text)))throw Error('主题强调色无效');if(!Array.isArray(s.palette)||s.palette.length<2||s.palette.length>12||!s.palette.every(col))throw Error('配色无效');
  for(const[k,v]of Object.entries(s.materials||{}))if(!C.M[k]||!col(v))throw Error('材质底色无效 '+k);for(const[k,r]of Object.entries(s.materialRecipes||{})){if(!C.M[k]||!col(r.color)||![r.roughness,r.metalness].every(v=>Number.isFinite(v)&&v>=0&&v<=1)||!['fabric','woven','leather','wood','stone','paint','plaster'].includes(r.surface))throw Error('材质配方无效 '+k);}
  if(!s.lighting||!Number.isFinite(s.lighting.temperature)||s.lighting.temperature<1800||s.lighting.temperature>8000)throw Error('色温范围为1800–8000K');for(const[k,min,max]of[['exposure',.4,1.5],['sun',0,4],['environment',.1,1.5],['reflection',0,1.8],['fixtureIntensity',0,100],['ambientIntensity',0,100]]){if(!Number.isFinite(s.lighting[k])||s.lighting[k]<min||s.lighting[k]>max)throw Error('风格灯光参数无效 '+k);}
  for(const k of ['intent','forms','materials','details','lighting','avoid'])if(typeof s.playbook?.[k]!=='string'||s.playbook[k].length>1500)throw Error('缺少playbook说明 '+k);return true;};
 C.applyStyleRecipe=function(s){C.validateStyle(s);C.activeStyle=s;for(const[k,m]of Object.entries(C.M)){const base=original[k];if(!base)continue;const r=s.materialRecipes[k];if(m.color)m.color.set(r?.color||s.materials?.[k]||base.color);m.roughness=r?.roughness??base.roughness;m.metalness=r?.metalness??base.metalness;
   m.map=base.map;m.normalMap=base.normalMap;if(m.normalScale&&base.normalScale)m.normalScale.copy(base.normalScale);
   if(r){const maps=C.materialAssets[r.surface];if(maps){m.map=maps.color||null;m.normalMap=maps.normal||null;if(m.normalScale)m.normalScale.set(r.surface==='fabric'?.28:.13,r.surface==='fabric'?.28:.13);}else if(['paint','plaster'].includes(r.surface)){m.map=null;m.normalMap=r.surface==='plaster'?C.materialAssets.plaster.normal:base.normalMap;}}
   m.userData.role=k;m.needsUpdate=true;}
 };
 C.styleForms=forms;
 C.styledArt=function(kind){const c=document.createElement('canvas');c.width=c.height=512;const ctx=c.getContext('2d'),p=C.activeStyle.palette;ctx.fillStyle=p[0];ctx.fillRect(0,0,512,512);
  if(kind==='ink'){for(let i=0;i<6;i++){ctx.beginPath();ctx.moveTo(0,400-i*18);for(let x=0;x<=512;x+=8)ctx.lineTo(x,340-i*28-55*Math.sin(x/115+i*.4)-22*Math.sin(x/35));ctx.lineTo(512,512);ctx.lineTo(0,512);ctx.closePath();ctx.fillStyle=`rgba(45,46,37,${.035+i*.015})`;ctx.fill();}ctx.fillStyle='#9b6650';ctx.fillRect(428,65,15,29);}
  else if(kind==='geometry'){for(let i=0;i<5;i++){ctx.fillStyle=p[(i+1)%p.length];ctx.fillRect(55+i*57,70+(i%2)*130,42,270-i*18);}ctx.fillStyle=p[2];ctx.beginPath();ctx.arc(365,345,58,0,Math.PI*2);ctx.fill();}
  else if(kind==='earth'){for(let i=0;i<8;i++){ctx.fillStyle=p[i%p.length];ctx.globalAlpha=.3;ctx.beginPath();ctx.ellipse(120+i*39,330-i*12,170-i*10,70+i*7,-.3,0,Math.PI*2);ctx.fill();}ctx.globalAlpha=1;}
  else {ctx.fillStyle=p[1];ctx.fillRect(100,240,180,235);ctx.beginPath();ctx.arc(190,240,90,Math.PI,0);ctx.fill();ctx.fillStyle=p[3];ctx.beginPath();ctx.arc(355,155,53,0,Math.PI*2);ctx.fill();ctx.strokeStyle=p[2];ctx.lineWidth=15;ctx.strokeRect(250,230,120,230);}
  const tex=C.texture(c);return new T.MeshStandardMaterial({name:'原创风格艺术 / '+kind,map:tex,roughness:1});
 };
})(window.CREAM,window.THREE);
