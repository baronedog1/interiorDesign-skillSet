

/* Neutral, deterministic offline PBR material assets. Role colors come from a style recipe. */
window.CREAM = window.CREAM || {};
(function(C,T){
'use strict';
let seed=73091;
const rand=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};
C.rand=rand;
function canvas(size=512){const c=document.createElement('canvas');c.width=c.height=size;return c;}
function tex(c,repeat=1){const t=new T.CanvasTexture(c);t.wrapS=t.wrapT=T.RepeatWrapping;t.repeat.set(repeat,repeat);t.colorSpace=T.SRGBColorSpace;t.anisotropy=4;return t;}
function noiseMap(kind){
 const c=canvas(kind==='wood'?1024:512),ctx=c.getContext('2d',{willReadFrequently:true}),s=c.width;
 ctx.fillStyle=kind==='wood'?'#c5a885':kind==='stone'?'#dfd2be':kind==='fabric'?'#eee8dc':'#f0ece3';ctx.fillRect(0,0,s,s);
 const im=ctx.getImageData(0,0,s,s),d=im.data;
 for(let y=0;y<s;y++)for(let x=0;x<s;x++){
  const i=(y*s+x)*4;let n=(rand()-.5)*(kind==='fabric'?28:kind==='stone'?12:9);
  if(kind==='wood') n+=4*Math.sin(x*.16+2*Math.sin(y*.005)) + 2*Math.sin(x*.76+y*.003);
  if(kind==='stone') n+=4*Math.sin(y*.038+6*Math.sin(x*.003))+2*Math.sin(y*.17+Math.sin(x*.06));
  if(kind==='fabric') n+=((x%4===0)?-13:0)+((y%4===0)?-10:0);
  d[i]+=n;d[i+1]+=n;d[i+2]+=n;
 }
 ctx.putImageData(im,0,0);
 if(kind==='wood'){
  for(let i=0;i<700;i++){const x=rand()*s;ctx.beginPath();ctx.moveTo(x,0);for(let y=0;y<=s;y+=16)ctx.lineTo(x+Math.sin(y/150+i)*1.8+Math.sin(y/40+i)*.4,y);ctx.strokeStyle=`rgba(84,61,35,${.015+rand()*.10})`;ctx.lineWidth=.25+rand()*1.25;ctx.stroke();}
 }else if(kind==='stone'){
  for(let i=0;i<3600;i++){ctx.fillStyle=`rgba(102,88,61,${.035+rand()*.13})`;ctx.beginPath();ctx.ellipse(rand()*s,rand()*s,.25+rand()*2,.2+rand()*.7,0,0,7);ctx.fill();}
 }
 return c;
}
function normalFrom(c,strength=2){
 const s=c.width,ctx=c.getContext('2d',{willReadFrequently:true}),src=ctx.getImageData(0,0,s,s).data,out=canvas(s),o=out.getContext('2d',{willReadFrequently:true}),im=o.createImageData(s,s);
 const val=(x,y)=>src[(((y+s)%s)*s+(x+s)%s)*4]/255;
 for(let y=0;y<s;y++)for(let x=0;x<s;x++){const i=(y*s+x)*4;let dx=(val(x+1,y)-val(x-1,y))*strength,dy=(val(x,y+1)-val(x,y-1))*strength;const l=Math.sqrt(dx*dx+dy*dy+1);im.data[i]=(1-dx/l)*127.5;im.data[i+1]=(1-dy/l)*127.5;im.data[i+2]=(1+1/l)*127.5;im.data[i+3]=255;}
 o.putImageData(im,0,0);const t=tex(out);t.colorSpace=T.NoColorSpace;return t;
}
const woodC=noiseMap('wood'),stoneC=noiseMap('stone'),fabricC=noiseMap('fabric'),plasterC=noiseMap('plaster');
// Base maps carry detail, not a fixed cream tint. Theme colors remain independent.
for(const c of [woodC,stoneC,fabricC,plasterC]){const ctx=c.getContext('2d'),im=ctx.getImageData(0,0,c.width,c.height);for(let i=0;i<im.data.length;i+=4){const v=Math.min(255,218+(im.data[i]+im.data[i+1]+im.data[i+2])/3-190);im.data[i]=im.data[i+1]=im.data[i+2]=v;}ctx.putImageData(im,0,0);}
const wood=tex(woodC),stone=tex(stoneC),fabric=tex(fabricC,6),plaster=tex(plasterC,2);
const woodN=normalFrom(woodC,1.1),stoneN=normalFrom(stoneC,1.4),fabricN=normalFrom(fabricC,2.5),plasterN=normalFrom(plasterC,.7);
fabricN.repeat.set(6,6);
const leatherC=canvas(256),lx=leatherC.getContext('2d'),li=lx.createImageData(256,256);for(let i=0;i<li.data.length;i+=4){const v=224+Math.floor(rand()*26);li.data[i]=li.data[i+1]=li.data[i+2]=v;li.data[i+3]=255;}lx.putImageData(li,0,0);
C.materialAssets={wood:{color:wood,normal:woodN},stone:{color:stone,normal:stoneN},fabric:{color:fabric,normal:fabricN},woven:{color:fabric,normal:fabricN},plaster:{color:plaster,normal:plasterN},leather:{color:tex(leatherC,4),normal:normalFrom(leatherC,.7)}};

function mat(name,color,roughness=.75,extra={}){const m=new T.MeshStandardMaterial({color,roughness,...extra});m.name=name;return m;}
C.mat=mat;
C.M={
 plaster:mat('温润石灰基涂料','#f0e8d9',.96,{normalMap:plasterN,normalScale:new T.Vector2(.12,.12)}),
 cream:mat('象牙白哑光烤漆','#f1e6d4',.64),
 porcelain:mat('釉面陶瓷','#fff7e8',.2),
 oak:mat('浅烟熏白橡木','#eee5d7',.68,{map:wood,normalMap:woodN,normalScale:new T.Vector2(.16,.16)}),
 walnut:mat('浅胡桃木','#937352',.67,{map:wood,normalMap:woodN}),
 travertine:mat('米色洞石','#fff4e1',.7,{map:stone,normalMap:stoneN,normalScale:new T.Vector2(.35,.35)}),
 linen:mat('自然亚麻织物','#fcf3df',.96,{map:fabric,normalMap:fabricN,normalScale:new T.Vector2(.40,.40)}),
 boucle:mat('奶油圈圈绒','#fff9ed',.98,{map:fabric,normalMap:fabricN,normalScale:new T.Vector2(.85,.85)}),
 sand:mat('燕麦色织物','#c9b59b',.95,{map:fabric,normalMap:fabricN}),
 clay:mat('陶土色棉麻','#b1856a',.93,{map:fabric,normalMap:fabricN}),
 sage:mat('鼠尾草绿织物','#a7ad91',.95,{map:fabric,normalMap:fabricN}),
 rug:mat('手织羊毛地毯','#e7d8bc',.98,{map:fabric,normalMap:fabricN,normalScale:new T.Vector2(.8,.8)}),
 bronze:mat('香槟拉丝金属','#aa8d62',.3,{metalness:.78}),
 black:mat('深古铜五金','#322e28',.38,{metalness:.55}),
 mirror:new T.MeshStandardMaterial({name:'镜面（环境反射）',color:'#e4e3df',metalness:1,roughness:.035}),
 glass:new T.MeshPhysicalMaterial({name:'透明低铁玻璃',color:'#e6f1ed',transparent:true,opacity:.17,roughness:.08,metalness:.08,depthWrite:false,side:T.DoubleSide}),
 sheer:new T.MeshStandardMaterial({name:'透光白纱',color:'#fff9ec',roughness:1,transparent:true,opacity:.52,side:T.DoubleSide,depthWrite:false}),
 leaf:mat('橄榄叶','#6f7a48',.88),leaf2:mat('尤加利叶','#88907a',.89),
 soil:mat('盆栽基质','#453a2e',1),
 dark:mat('阴缝 / 橡胶','#39332c',.88),
 led:new T.MeshStandardMaterial({name:'2700K线性柔光',color:'#fff1ca',emissive:'#ffdf9b',emissiveIntensity:1.6,roughness:.45}),
 screen:mat('关闭电视屏幕','#242c2b',.15,{metalness:.25}),
 white:mat('暖白纸','#f6f0e5',.93),
};
C.texture=tex;
C.canvas=canvas;
C.makeArt=function(style=0){
 const c=canvas(512),x=c.getContext('2d',{willReadFrequently:true});x.fillStyle=['#ded5c4','#ebe3d4','#d5c1a5'][style%3];x.fillRect(0,0,512,512);
 const cols=['#b4a183','#7b715f','#ede6d9','#8b7559'];
 x.fillStyle=cols[style%4];x.beginPath();x.ellipse(180,320,125,235,.22,0,7);x.fill();
 x.fillStyle='#eee6d5';x.fillRect(250,220,190,300);x.beginPath();x.arc(345,220,95,Math.PI,0);x.fill();
 x.strokeStyle='#5f6152';x.lineWidth=6;x.beginPath();x.moveTo(70,450);x.bezierCurveTo(460,260,60,210,410,85);x.stroke();
 x.fillStyle='#987d63';x.beginPath();x.arc(360,125,37,0,7);x.fill();
 for(let i=0;i<15000;i++){x.fillStyle=`rgba(72,61,43,${rand()*.025})`;x.fillRect(rand()*512,rand()*512,1,1);}
 return new T.MeshStandardMaterial({name:'原创抽象艺术画',map:tex(c),roughness:1});
};
C.contactTexture=(()=>{const c=canvas(128),x=c.getContext('2d',{willReadFrequently:true}),g=x.createRadialGradient(64,64,3,64,64,64);g.addColorStop(0,'rgba(54,40,23,0.27)');g.addColorStop(.5,'rgba(54,40,23,0.14)');g.addColorStop(1,'rgba(54,40,23,0)');x.fillStyle=g;x.fillRect(0,0,128,128);return tex(c);})();
})(window.CREAM,window.THREE);


