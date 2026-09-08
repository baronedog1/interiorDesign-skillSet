/* Geometry families shared by all projects. Each result is normalized by instantiate;
 * switching style changes silhouette/details, never the placement's footprint. */
(function(C,T){'use strict';const B=C.box,G=C.group,Y=C.cyl,M=C.M;
 function feet(g,w,d,h,kind){for(const x of[-w/2,w/2])for(const z of[-d/2,d/2]){if(kind==='tapered'||kind==='timber'){const m=Y(g,.045,.026,h,x,h/2,z,M.walnut,16);m.rotation.z=-Math.sign(x)*.08;}else B(g,.045,h,.045,x,h/2,z,kind==='linear'?M.bronze:M.walnut,.005);}}
 function top(g,w,d,y,material,kind,h=.07){if(['oval','organic'].includes(kind)){const m=Y(g,w/2,w/2,h,0,y,0,material,64);m.scale.z=d/w;if(kind==='organic'){const a=m.geometry.attributes.position;for(let i=0;i<a.count;i++){const x=a.getX(i),z=a.getZ(i),t=Math.atan2(z,x),f=1+.065*Math.sin(t*3)+.035*Math.cos(t*5);a.setX(i,x*f);a.setZ(i,z*f);}m.geometry.computeVertexNormals();}return m;}return B(g,w,h,d,0,y,0,material,kind==='tapered'?.06:.016);}
 function flutes(g,w,h,y,z,material,spacing=.06){for(let x=-w/2+.02;x<w/2;x+=spacing)B(g,.022,h,.024,x,y,z,material,.007);}
 function cushion(g,w,h,d,x,y,z,m){return C.pillow(g,w,h,d,x,y,z,m);}
 function sofa(g,f,shape={}){const cloud=f==='cloud',low=f==='low',timber=['timber','lattice'].includes(f),r=cloud?.12:low?.13:.045,baseY=low?.15:.28,seats=shape.seats||3;
  if(!low)feet(g,2.9,.79,.20,f==='linear'?'linear':timber?'timber':'rounded');B(g,3.24,.18,1.05,0,baseY,0,timber?M.walnut:M.boucle,r);
  for(let i=0;i<seats;i++){const x=(i-(seats-1)/2)*3.06/seats,w=3.06/seats;B(g,w-.02,.20,.86,x,baseY+.18,.065,M.boucle,r);B(g,w+.01,.50,.21,x,baseY+.47,-.405,timber?M.oak:M.boucle,r);if(timber)cushion(g,w-.08,.47,.15,x,baseY+.47,-.25,M.linen);}
  for(const x of[-1.60,1.60]){if(timber){B(g,.09,.43,.98,x,baseY+.25,0,M.walnut,.018);B(g,.15,.065,1.03,x,baseY+.485,0,M.oak,.03);if(f==='lattice')for(let z=-.36;z<.4;z+=.12)B(g,.035,.35,.025,x,baseY+.265,z,M.walnut,.002);}else B(g,.20,.39,.99,x,baseY+.28,0,M.boucle,r);}
  // Shape belongs to component selection, not to a room or style preset.
  if(shape.chaise!==false){B(g,1.02,.18,.72,-1.03,baseY,.88,timber?M.walnut:M.boucle,r);B(g,1.02,.2,.72,-1.03,baseY+.18,.88,M.boucle,r);}
  const colors=[M.sand,M.linen,M.sage];for(let i=0;i<3;i++){const p=cushion(g,.43,.40,.15,-1+i,baseY+.52,-.12,colors[i]);p.rotation.z=(i-1)*.08;}
  if(low){B(g,3.19,.055,1.00,0,.035,.01,M.walnut,.01);}
 }
 function bed(g,f){const w=1.96,soft=f==='soft',platform=f==='platform',timber=['timber','lattice'].includes(f);const y=platform?.18:.29;
  B(g,w,.23,2.17,0,y,0,timber||platform?M.walnut:M.sand,soft?.10:.035);if(!platform)feet(g,1.69,1.80,.20,'timber');B(g,1.88,.22,2.0,0,y+.21,.04,M.linen,.09);B(g,1.89,.12,1.39,0,y+.345,.35,M.boucle,.06);
  B(g,w+.08,soft?1.14:1.03,.13,0,.62,-1.065,timber||platform?M.oak:M.sand,soft?.13:.024);
  if(f==='panel'){for(const x of[-.48,.48])B(g,.94,.65,.04,x,.77,-.977,M.linen,.028);}
  if(f==='lattice'){B(g,1.88,.66,.025,0,.74,-.981,M.linen,.005);flutes(g,1.82,.60,.76,-.953,M.walnut,.09);}
  if(f==='timber'){B(g,1.85,.54,.028,0,.74,-.98,M.walnut,.018);B(g,1.62,.03,.02,0,.50,-.955,M.bronze,.004);}
  for(const x of[-.47,.47]){const p=cushion(g,.76,.17,.47,x,y+.39,-.66,M.linen);p.rotation.y=x*.08;cushion(g,.70,.16,.40,x,y+.40,-.41,M.white);}
  B(g,1.89,.025,.47,0,y+.422,.70,M.sage,.01);for(let i=0;i<9;i++)B(g,.013,.013,.45,-.80+i*.20,y+.442,.70,M.linen,.004);
 }
 function chair(g,f,lounge=false){const w=lounge?.75:.48,d=lounge?.73:.49,y=.44;feet(g,w*.76,d*.72,.43,f==='linear'?'linear':'timber');B(g,w,.085,d,0,y,0,M.walnut,.024);cushion(g,w*.97,.10,d*.96,0,y+.08,.018,lounge?M.sand:M.linen);
  const soft=['rounded','organic'].includes(f);B(g,w+.025,.35,.08,0,.79,-d*.42,soft?M.boucle:M.oak,soft?.05:.015);
  if(f==='lattice'){B(g,w-.07,.30,.035,0,.79,-d*.34,M.linen,.005);flutes(g,w-.07,.28,.79,-d*.305,M.walnut,.068);}
  if(lounge||f==='timber'||f==='lattice')for(const x of[-w*.5,w*.5]){B(g,.045,.22,.045,x,.6,-d*.28,M.walnut,.009);B(g,.056,.045,d*.93,x,.70,.00,M.oak,.014);}
 }
 function table(g,f,coffee=false){const w=coffee?1.42:1.04,d=coffee?.89:1.98,y=coffee?.41:.76;const wood=['tapered','trestle'].includes(f),mat=wood?M.oak:M.travertine;top(g,w,d,y,mat,f,coffee?.09:.07);
  if(['oval','organic'].includes(f)){for(const z of (coffee?[0]:[-.52,.52])){const m=Y(g,coffee?.22:.22,coffee?.25:.24,y-.055,coffee?-.21:0,(y-.055)/2,z,M.oak,32);if(f==='oval')flutes(g,.37,y-.075,(y-.055)/2,z+.20,M.oak,.045);}}
  else if(f==='trestle'){for(const z of[-d*.30,d*.30]){B(g,w*.73,y-.04,.055,0,(y-.04)/2,z,M.walnut,.01);B(g,w*.89,.055,.20,0,.04,z,M.walnut,.009);}B(g,.06,.05,d*.69,0,.26,0,M.walnut,.005);}
  else feet(g,w*.82,d*.80,y-.04,f==='tapered'?'tapered':'linear');
  if(coffee){if(['oval','organic'].includes(f)){const m=Y(g,.29,.29,.035,.52,.51,.20,M.walnut,40);Y(g,.105,.105,.475,.52,.253,.20,M.walnut,24);}C.book(g,.28,.20,.035,-.20,y+.045,.02,'#98866a');C.vase(g,.17,y+.05,-.12,.13,.065,M.cream);if(f==='trestle'){B(g,.45,.02,.25,.27,y+.055,.06,M.walnut,.012);for(const x of[.14,.3,.42])Y(g,.035,.032,.055,x,y+.092,.08,M.porcelain,20);}}
  else {for(const z of[-.59,.0,.59])for(const x of[-.34,.34]){Y(g,.10,.10,.009,x,y+.043,z,M.porcelain,32);C.rod(g,[x+.12,y+.053,z-.07],[x+.12,y+.053,z+.07],.003,M.bronze);}C.vase(g,0,y+.05,.05,.20,.07,M.cream);}
 }
 function cabinet(g,f,wardrobe=false){const w=wardrobe?1.8:1.95,h=wardrobe?2.50:.82,d=wardrobe?.60:.43,y=wardrobe?h/2+.02:.48;const mat=['timber','lattice'].includes(f)?M.oak:f==='block'?M.travertine:M.cream;
  B(g,w,h,d,0,y,0,M.walnut,f==='block'?.025:.008);const count=wardrobe?3:3;
  for(let i=0;i<count;i++){const x=(i-(count-1)/2)*w/count;B(g,w/count-.012,h-.03,.03,x,y,d/2+.018,mat,.009);
   if(f==='fluted')flutes(g,w/count-.04,h-.06,y,d/2+.046,M.oak,.045);
   if(f==='lattice'){B(g,w/count-.09,h*.73,.013,x,y,d/2+.04,M.sand,.002);for(let xx=x-w/count*.40;xx<x+w/count*.41;xx+=.073)B(g,.021,h*.73,.021,xx,y,d/2+.054,M.walnut,.003);}
   if(f!=='flat'&&f!=='block')B(g,.075,.013,.025,x,y+h*.23,d/2+.07,M.bronze,.003);
  }if(!wardrobe){feet(g,w*.85,d*.8,.15,f==='timber'?'tapered':'linear');B(g,w+.04,.036,d+.02,0,y+h/2+.02,0,f==='timber'?M.oak:M.travertine,.015);}}
 function tv(g,f){const mat=f==='block'?M.plaster:f==='flat'?M.cream:M.travertine;B(g,3.15,2.60,.07,0,1.31,-.15,mat,.018);
  if(f==='timber'||f==='lattice'){B(g,.60,2.60,.065,1.27,1.31,-.095,M.walnut,.006);for(let x=1.02;x<1.53;x+=.06)B(g,.019,2.52,.033,x,1.31,-.045,M.oak,.003);}
  if(f==='fluted'){for(let x=-1.48;x<-1.0;x+=.06)B(g,.022,2.49,.025,x,1.32,-.098,M.oak,.006);}
  B(g,2.96,.26,.40,0,.39,.095,['timber','lattice'].includes(f)?M.walnut:M.oak,.02);for(let i=0;i<4;i++)B(g,.728,.209,.027,(i-1.5)*.741,.40,.307,f==='lattice'?M.oak:M.cream,.004);
  B(g,1.94,1.12,.05,-.17,1.54,-.073,M.black,.014);B(g,1.90,1.08,.009,-.17,1.54,-.041,M.screen,.008);C.vase(g,1.11,.54,.11,.25,.075,M.cream);
 }
 function pendant(g,f,table=false,floor=false){const pole=table?.31:floor?1.72:.58;
  if(table||floor){Y(g,table?.17:.23,table?.17:.23,.027,0,.02,0,M.walnut,32);C.rod(g,[0,.025,0],[0,pole-.11,0],.012,M.bronze);}
  else{B(g,.54,.036,.08,0,.576,0,M.bronze,.009);C.rod(g,[0,.558,0],[0,.27,0],.005,M.bronze);}
  const y=table?pole-.09:floor?pole-.08:.20;
  if(f==='linear'){B(g,table?.4:floor?.60:.98,.027,.064,0,y,0,M.bronze,.01);B(g,table?.36:floor?.56:.94,.012,.054,0,y-.017,0,M.led,.004);}
  else if(f==='sputnik'){for(const x of[-.34,0,.34]){C.rod(g,[0,y+.08,0],[x,y-.06,0],.008,M.bronze);C.sphere(g,.095,.095,.095,x,y-.06,0,M.led);}}
  else if(f==='paper'){const s=C.sphere(g,.30,.17,.23,0,y,0,M.linen);for(let i=0;i<8;i++){const yy=-.145+i*.04,rr=.30*Math.sqrt(Math.max(.01,1-(yy/.18)**2));C.ring(g,rr,.004,0,y+yy,0,M.oak,Math.PI/2);}}
  else if(f==='lantern'){Y(g,.19,.19,.30,0,y,0,M.linen,48);for(let i=0;i<12;i++){const a=i*Math.PI/6;C.rod(g,[.193*Math.cos(a),y-.154,.193*Math.sin(a)],[.193*Math.cos(a),y+.154,.193*Math.sin(a)],.005,M.walnut);}for(const yy of[y-.154,y+.154])C.ring(g,.195,.008,0,yy,0,M.walnut,Math.PI/2);}
  else{C.lathe(g,[[0,.12],[.11,.12],[.25,.016],[.28,-.083],[.27,-.095],[0,-.095]],0,y,0,M.cream);C.sphere(g,.08,.06,.08,0,y-.07,0,M.led);}
 }
 C.buildStyled=function(builder,parent,meta={}){const f=C.activeStyle.forms;const supported=['sofa','bed','chair','armchair','coffee','dining','wardrobe','sideboard','tv','pendant','tableLamp','floorLamp','art','rug'];if(!supported.includes(builder))return null;const g=G(parent,builder+' / '+C.activeStyle.name);
  if(builder==='sofa')sofa(g,f.sofa,meta.shape); else if(builder==='bed')bed(g,f.bed);else if(builder==='chair'||builder==='armchair')chair(g,f.chair,builder==='armchair');else if(builder==='coffee'||builder==='dining')table(g,f.tables,builder==='coffee');else if(builder==='wardrobe'||builder==='sideboard')cabinet(g,f.cabinet,builder==='wardrobe');else if(builder==='tv')tv(g,f.cabinet);else if(['pendant','tableLamp','floorLamp'].includes(builder))pendant(g,f.pendant,builder==='tableLamp',builder==='floorLamp');
  else if(builder==='art'){B(g,.86,1.06,.035,0,.53,0,M.walnut,.005);B(g,.81,1.01,.021,0,.53,.027,C.styledArt(f.art),.002);}
  else if(builder==='rug'){B(g,3.5,.024,2.8,0,.015,0,M.rug,.01);if(f.art==='geometry'){for(let x of[-1.3,1.3])B(g,.09,.002,2.50,x,.029,0,M.sage,.001);B(g,2.65,.002,.11,0,.029,1.07,M.sage,.001);}else if(f.art==='ink'){B(g,3.2,.002,2.5,0,.029,0,M.linen,.001);B(g,3.10,.002,2.40,0,.032,0,M.rug,.001);}}
  g.userData.styleVariant=builder+':'+(f[{sofa:'sofa',bed:'bed',chair:'chair',armchair:'chair',coffee:'tables',dining:'tables',wardrobe:'cabinet',sideboard:'cabinet',tv:'cabinet',pendant:'pendant',floorLamp:'pendant',tableLamp:'pendant',art:'art',rug:'art'}[builder]]);return g;
 };
})(window.CREAM,window.THREE);
