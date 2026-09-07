

/* Bespoke furniture and small-scale construction details. */
(function(C,T){
'use strict';
const M=C.M,B=C.box,G=C.group,cy=C.cyl,sp=C.sphere;
C.assets=[];
function asset(parent,name,x=0,z=0,rot=0){const g=G(parent,name,x,0,z,rot);g.userData.semantic=name;C.assets.push(g);return g;}
C.vase=function(p,x,y,z,h=.3,r=.12,mat=M.porcelain){return C.lathe(p,[[0,0],[r*.7,0],[r*.9,.04*h],[r,h*.28],[r*.95,h*.50],[r*.58,h*.8],[r*.50,h],[r*.41,h],[r*.40,h*.85],[0,h*.1]],x,y,z,mat,'手作陶瓶 / 空心瓶口');};
C.bouquet=function(p,x,y,z,scale=1){
 const g=G(p,'尤加利枝花艺',x,y,z);g.scale.setScalar(scale);C.vase(g,0,0,0,.28,.13,M.travertine);
 for(let i=0;i<7;i++){const a=i*2.4,ex=Math.cos(a)*(.11+C.rand()*.12),ez=Math.sin(a)*.18,h=.55+C.rand()*.23;
  C.tube(g,[[0,.1,0],[ex*.3,.43,ez*.3],[ex,h,ez]],.005,M.walnut);
  for(let j=0;j<5;j++){const t=.45+j*.11,side=j%2?1:-1;const leaf=sp(g,.047,.008,.085,ex*t+side*.035,h*t+.1,ez*t,M.leaf2,'尤加利叶片');leaf.rotation.set(C.rand(),a+j,.4*side);}
 }return g;
};
C.plant=function(p,x,z,h=1.9){
 const g=asset(p,'室内橄榄树 / 陶盆',x,z);const scale=h/1.9;g.scale.setScalar(scale);
 C.vase(g,0,.018,0,.44,.235,M.travertine);cy(g,.18,.18,.03,0,.39,0,M.soil);
 C.tube(g,[[0,.29,0],[.03,.82,.02],[-.025,1.27,0],[.09,1.77,.015]],.021,M.walnut,false,'自然弯曲树干');
 const leafG=new T.SphereGeometry(1,10,6),inst=new T.InstancedMesh(leafG,M.leaf,144),dummy=new T.Object3D();
 let li=0;
 for(let i=0;i<12;i++){const a=i*2.399,by=.72+i*.077,rr=.29+.12*Math.sin(i/12*Math.PI),end=[Math.cos(a)*rr,by+.32,Math.sin(a)*rr];C.tube(g,[[.015,by,0],[end[0]*.7,by+.14,end[2]*.7],end],.0065,M.walnut);
  for(let j=0;j<12;j++){const t=.3+j*.055;dummy.position.set(end[0]*t+(C.rand()-.5)*.13,by+(end[1]-by)*t+(C.rand()-.4)*.10,end[2]*t+(C.rand()-.5)*.13);dummy.rotation.set(C.rand()*1.2,C.rand()*6.28,C.rand()*.8);dummy.scale.set(.025,.006,.068);dummy.updateMatrix();inst.setMatrixAt(li++,dummy.matrix);}
 }
 inst.castShadow=true;inst.receiveShadow=true;inst.name='144枚独立橄榄叶';g.add(inst);return g;
};
C.rug=function(p,w,d,x,z,mat=M.rug){const g=asset(p,'手工织毯 / 包边',x,z);B(g,w,.023,d,0,.02,0,mat,.011);C.contact(g,w+.25,d+.25,0,0,.003);
 for(const s of [-1,1])B(g,w-.10,.003,.026,0,.033,s*(d/2-.035),M.linen,.001,'地毯锁边');
 return g;
};
C.lamp=function(p,x,y,z,scale=1){const g=G(p,'蘑菇台灯',x,y,z);g.scale.setScalar(scale);
 cy(g,.10,.12,.028,0,.014,0,M.bronze);cy(g,.044,.047,.26,0,.145,0,M.cream);C.lathe(g,[[0,.32],[.06,.335],[.135,.32],[.20,.27],[.215,.24],[.21,.225],[.04,.225]],0,0,0,M.cream,'磨砂蘑菇灯罩');cy(g,.18,.18,.004,0,.229,0,M.led);return g;};
C.downlight=function(p,x,z){cy(p,.062,.062,.022,x,2.773,z,M.cream);cy(p,.039,.039,.024,x,2.759,z,M.black);cy(p,.031,.031,.025,x,2.745,z,M.led);};
C.pendant=function(p,x,z,style='paper',drop=.65){const g=G(p,'吊灯 / 吊线与顶盘',x,0,z);cy(g,.065,.065,.026,0,2.812,0,M.cream);C.rod(g,[0,2.80,0],[0,2.80-drop,0],.006,M.bronze);
 if(style==='paper'){
  sp(g,.37,.22,.37,0,2.80-drop,0,M.linen,'和纸灯笼');
  for(let i=0;i<13;i++){const yy=-.20+i*.032;const rr=.37*Math.sqrt(Math.max(.01,1-(yy/.23)**2));C.ring(g,rr,.002,0,2.80-drop+yy,0,M.cream,Math.PI/2);}
 }else{
  C.lathe(g,[[0,.20],[.09,.19],[.19,.12],[.28,0],[.28,-.018],[.12,-.035]],0,2.8-drop,0,M.travertine,'洞石飞碟吊灯');cy(g,.21,.21,.007,0,2.8-drop-.025,0,M.led);
 }return g;};
C.wardrobe=function(p,w,x,z,rot=0,h=2.55){const g=asset(p,'通顶衣柜 / 独立门板与把手',x,z,rot);B(g,w,h,.59,0,h/2,0,M.oak,.013);const n=Math.round(w/.56),dw=w/n;
 B(g,w-.05,.08,.54,0,.045,0,M.dark,.003,'柜脚踢空');
 for(let i=0;i<n;i++){const xx=-w/2+(i+.5)*dw;B(g,dw-.012,h-.10,.038,xx,h/2+.025,.309,M.cream,.009,'衣柜独立门板');B(g,.014,.31,.03,xx+(i%2?-.18:.18),1.10,.348,M.bronze,.006,'竖向金属拉手');}
 B(g,w,.02,.027,0,h-.11,.33,M.bronze,.003,'通顶柜压边');return g;};
C.chair=function(p,x,z,rot=0,mat=M.linen){const g=asset(p,'曲木软包餐椅',x,z,rot);
 for(const sx of [-1,1])for(const sz of [-1,1])C.rod(g,[sx*.19,.045,sz*.20],[sx*.16,.46,sz*.16],.022,M.oak,'外撇实木椅腿');
 B(g,.47,.08,.45,0,.43,0,M.oak,.045);C.pillow(g,.46,.09,.44,0,.486,0,mat);
 const bg=B(g,.48,.36,.10,0,.735,.205,M.oak,.045);bg.rotation.x=-.10;
 const bc=C.pillow(g,.43,.29,.075,0,.74,.142,mat);bc.rotation.x=-.10;
 for(const s of [-1,1])C.rod(g,[s*.18,.47,.19],[s*.18,.87,.23],.015,M.oak);return g;};
C.sideTable=function(p,x,z,style=0){const g=asset(p,'床头边几',x,z);
 if(style===0){cy(g,.24,.23,.034,0,.47,0,M.travertine);cy(g,.11,.14,.43,0,.235,0,M.oak);
  for(let i=0;i<22;i++){const a=i*Math.PI*2/22;cy(g,.008,.008,.415,Math.cos(a)*.14,.235,Math.sin(a)*.14,M.oak,8,'边几竖向木纹凹槽');}
 }else{B(g,.49,.38,.40,0,.29,0,M.oak,.045);B(g,.44,.145,.02,0,.355,.205,M.cream,.01);B(g,.44,.145,.02,0,.193,.205,M.cream,.01);cy(g,.016,.016,.021,0,.35,.226,M.bronze,16).rotation.x=Math.PI/2;}
 C.contact(g,.8,.7,0,0);return g;};
function bedCloth(g,w,len,mat){
 const nu=64,nv=72,verts=[],uv=[],ix=[];
 for(let j=0;j<=nv;j++)for(let i=0;i<=nu;i++){
  const u=i/nu,v=j/nv,x=(u-.5)*(w+.24),z=-.63+v*(len/2+.80),side=Math.max(0,(Math.abs(x)-w/2)/.12),foot=Math.max(0,(z-(len/2-.04))/.21);
  const folds=.006*Math.sin(x*32+z*8)+.008*Math.sin(x*18-z*6)+.003*Math.sin(z*43+x*7);
  let y=.647+folds-.16*side**1.4-.235*Math.min(1,foot)**1.5;
  verts.push(x,y,z);uv.push(u*2,v*2);
 }
 for(let j=0;j<nv;j++)for(let i=0;i<nu;i++){const a=j*(nu+1)+i,b=a+nu+1;ix.push(a,b,a+1,a+1,b,b+1);}
 const geo=new T.BufferGeometry();geo.setAttribute('position',new T.Float32BufferAttribute(verts,3));geo.setAttribute('uv',new T.Float32BufferAttribute(uv,2));geo.setIndex(ix);geo.computeVertexNormals();const material=mat.clone();material.side=T.DoubleSide;C.mesh(g,geo,material,'布料网格 / 自然褶皱与垂边');
 const strip=B(g,w+.08,.035,.23,0,.678,-.54,mat,.016,'被头折边');strip.rotation.x=.025;
}
C.bed=function(p,x,z,w=1.8,rot=0,accent=M.sand){const len=2.12,g=asset(p,'软包床 / 床品 / 分层结构',x,z,rot);
 C.contact(g,w+.65,len+.5,0,0);
 for(const sx of [-1,1])for(const sz of [-1,1])cy(g,.033,.04,.14,sx*(w/2-.14),.08,sz*.86,M.walnut,16);
 B(g,w+.14,.28,len+.1,0,.275,0,M.linen,.12,'圆角软包床框');B(g,w,.21,len,0,.505,0,M.boucle,.08,'独立床垫');
 B(g,w+.28,1.12,.15,0,.68,-len/2-.055,M.linen,.073,'弧角软包床头');
 for(let i=0;i<5;i++)B(g,(w+.23)/5-.008,.80,.047,-(w+.23)/2+(i+.5)*(w+.23)/5,.77,-len/2+.024,M.linen,.022,'床头纵向软包分片');
 bedCloth(g,w,len,M.linen);
 for(const s of [-1,1]){
  const p1=C.pillow(g,w*.45,.18,.45,s*w*.25,.72,-.73,M.boucle,s*.025);p1.rotation.x=.16;
  const p2=C.pillow(g,w*.37,.35,.16,s*w*.245,.84,-.68,accent,s*.055);p2.rotation.x=.21;
 }
 // A draped runner with individual folds, not a flat color rectangle.
 const cloth=new T.PlaneGeometry(w+.2,.62,52,30),pp=cloth.attributes.position;
 for(let i=0;i<pp.count;i++){const xx=pp.getX(i),zz=.54+pp.getY(i),side=Math.max(0,(Math.abs(xx)-w/2)/.12);const surface=.647+.006*Math.sin(xx*32+zz*8)+.008*Math.sin(xx*18-zz*6)+.003*Math.sin(zz*43+xx*7)-.16*side**1.4;pp.setXYZ(i,xx,surface+.018+.003*Math.sin(xx*20+zz*2),zz);}
 cloth.computeVertexNormals();const cm=accent.clone();cm.side=T.DoubleSide;C.mesh(g,cloth,cm,'床尾搭毯 / 波褶布料');
 return g;
};
C.desk=function(p,x,z,w=1.5,rot=0){const g=asset(p,'窗边工作台 / 写字台',x,z,rot);B(g,w,.045,.57,0,.755,0,M.oak,.014);
 for(const s of [-1,1])B(g,.042,.71,.49,s*(w/2-.12),.365,0,M.oak,.009);
 B(g,.42,.16,.46,w/2-.26,.64,0,M.cream,.018);B(g,.11,.012,.025,w/2-.26,.66,.246,M.bronze,.004);
 B(g,.48,.013,.31,-.22,.79,.035,M.black,.014,'笔记本电脑键盘');const screen=B(g,.47,.30,.014,-.22,.943,-.104,M.black,.011,'笔记本电脑屏幕');screen.rotation.x=-.13;
 B(g,.425,.254,.004,-.22,.94,-.091,C.mat('电子墨色屏幕','#9aabac',.7),.005);
 C.lamp(g,w/2-.23,.781,-.09,.64);C.book(g,.18,.23,.028,-w/2+.2,.78,.02,'#a59c82');
 cy(g,.039,.03,.092,w/2-.21,.83,.16,M.porcelain);return g;};
C.shelf=function(p,x,z,w=1.45,rot=0){const g=asset(p,'开放书架 / 陈列格',x,z,rot);
 for(const xx of [-w/2,w/2])B(g,.026,2.25,.28,xx,1.13,0,M.oak,.005);
 for(let j=0;j<5;j++){const y=.2+j*.45;B(g,w,.026,.29,0,y,0,M.oak,.005);
  if(j%2===0){for(let i=0;i<5;i++){const b=C.book(g,.043,.18,.24,-w/2+.09+i*.05,y+.017,.015,['#a99b85','#c2b79f','#777f70','#e1d4bd','#957d65'][i]);b.rotation.z=i===4?-.12:0;}}
  else{C.vase(g,-w*.23,y+.018,0,.19,.075,M.cream);C.book(g,.26,.20,.032,w*.20,y+.018,0,'#c1b198');}
 }return g;};
C.switchPlate=function(p,x,y,z,rot=0){const g=G(p,'墙面开关 / 插座',x,y,z,rot);B(g,.083,.083,.009,0,0,0,M.cream,.008);B(g,.032,.05,.009,-.018,0,.008,M.white,.002);B(g,.032,.05,.009,.018,0,.008,M.white,.002);};
C.sofa=function(p,x,z){const g=asset(p,'模块式圆润云朵沙发',x,z);
 C.contact(g,3.9,1.65,0,0);
 for(const xx of [-1.16,0,1.16])for(const zz of [-.32,.30])cy(g,.035,.04,.12,xx,.08,zz,M.walnut,12);
 B(g,3.16,.28,1.0,0,.29,0,M.boucle,.13,'沙发圆角承托底座');
 for(let i=0;i<3;i++){const xx=(i-1)*.93;B(g,.918,.21,.83,xx,.515,-.07,M.boucle,.10,'独立座垫');const back=B(g,.95,.56,.23,xx,.82,.37,M.boucle,.11,'柔软靠背');back.rotation.x=-.09;}
 for(const s of [-1,1])B(g,.24,.43,.93,s*1.50,.62,0,M.boucle,.115,'圆弧扶手');
 const colors=[M.linen,M.sand,M.clay,M.linen,M.sage];
 for(let i=0;i<5;i++){const p=C.pillow(g,.47,.46,.16,-1.16+i*.58,.81,.14,colors[i],(i-2)*.06);p.rotation.x=-.18;}
 // Chaise module joins the left seat with a visible upholstered seam.
 B(g,.96,.26,.78,-.98,.28,-.88,M.boucle,.12,'贵妃脚踏底座');B(g,.96,.20,.77,-.98,.50,-.88,M.boucle,.09,'贵妃脚踏软垫');
 return g;
};
C.armchair=function(p,x,z,rot=0){const g=asset(p,'休闲单椅 / 圈圈绒',x,z,rot);
 cy(g,.29,.33,.12,0,.12,0,M.oak,40);B(g,.69,.27,.67,0,.37,0,M.sand,.13);B(g,.68,.15,.61,0,.51,-.045,M.boucle,.072);
 const bk=B(g,.74,.50,.17,0,.74,.24,M.boucle,.08);bk.rotation.x=-.15;
 for(const s of [-1,1])B(g,.14,.28,.61,s*.34,.62,0,M.boucle,.068);
 C.pillow(g,.36,.32,.12,0,.72,.10,M.linen,.07);return g;
};

})(window.CREAM,window.THREE);
