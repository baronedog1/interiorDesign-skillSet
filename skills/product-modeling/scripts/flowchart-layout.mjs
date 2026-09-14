export const PAGE_WIDTH = 2400;
export const PAGE_HEIGHT = 1697;

export const escapeXml = (value) => String(value)
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;');

export function textLines(x, y, lines, options = {}) {
  const size = options.size ?? 17;
  const lineHeight = options.lineHeight ?? Math.round(size * 1.35);
  const anchor = options.anchor ?? 'middle';
  const weight = options.weight ?? 450;
  const fill = options.fill ?? '#111';
  return `<text x="${x}" y="${y}" text-anchor="${anchor}" font-size="${size}" font-weight="${weight}" fill="${fill}">${lines.map((line, index) => `<tspan x="${x}" dy="${index === 0 ? 0 : lineHeight}">${escapeXml(line)}</tspan>`).join('')}</text>`;
}

export function flowNode(type, x, y, w, h, title, lines = [], options = {}) {
  const fill = options.fill ?? (type === 'process' ? '#f1f1f1' : '#fff');
  const stroke = options.stroke ?? '#111';
  const strokeWidth = options.strokeWidth ?? 2;
  let shape = '';
  if (type === 'io') {
    const slant = Math.min(26, w * 0.08);
    shape = `<polygon points="${x + slant},${y} ${x + w},${y} ${x + w - slant},${y + h} ${x},${y + h}" fill="${fill}" stroke="${stroke}" stroke-width="${strokeWidth}"/>`;
  } else if (type === 'reference') {
    shape = `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="5" fill="${fill}" stroke="${stroke}" stroke-width="${strokeWidth}" stroke-dasharray="9 7"/>`;
  } else if (type === 'decision') {
    shape = `<polygon points="${x + w / 2},${y} ${x + w},${y + h / 2} ${x + w / 2},${y + h} ${x},${y + h / 2}" fill="${fill}" stroke="${stroke}" stroke-width="${strokeWidth}"/>`;
  } else if (type === 'store') {
    const radiusY = 13;
    shape = `<path d="M ${x} ${y + radiusY} A ${w / 2} ${radiusY} 0 0 1 ${x + w} ${y + radiusY} L ${x + w} ${y + h - radiusY} A ${w / 2} ${radiusY} 0 0 1 ${x} ${y + h - radiusY} Z" fill="${fill}" stroke="${stroke}" stroke-width="${strokeWidth}"/>
      <ellipse cx="${x + w / 2}" cy="${y + radiusY}" rx="${w / 2}" ry="${radiusY}" fill="${fill}" stroke="${stroke}" stroke-width="${strokeWidth}"/>
      <path d="M ${x} ${y + h - radiusY} A ${w / 2} ${radiusY} 0 0 0 ${x + w} ${y + h - radiusY}" fill="none" stroke="${stroke}" stroke-width="${strokeWidth}"/>`;
  } else {
    shape = `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="5" fill="${fill}" stroke="${stroke}" stroke-width="${strokeWidth}"/>`;
  }

  const layout = fitNode(type,w,h,title,lines,options);
  const {titleLines,bodyLines,titleSize,bodySize,lineHeight,blockHeight}=layout;
  const top=y+(h-blockHeight)/2+(type==='store'?10:0);
  let label=textLines(x+w/2,top+titleSize,titleLines,{size:titleSize,lineHeight,weight:700});
  const safeW=type==='decision'?w*.6:w-(type==='io'?72:40);
  const secondaryStart=Number.isInteger(options.secondaryFrom)
    ? lines.slice(0,options.secondaryFrom).flatMap(v=>wrap(v,safeW,bodySize)).length : bodyLines.length;
  // Keep the measured line boxes; file references are visually secondary.
  for(const [i,line] of bodyLines.entries())label+=textLines(x+(w-safeW)/2,top+titleLines.length*lineHeight+bodySize+10+i*lineHeight,[line],{size:i>=secondaryStart?bodySize*.82:bodySize,lineHeight,weight:430,anchor:'start',fill:i>=secondaryStart?'#52616b':'#111'});
  return '<g>'+shape+label+'</g>';
}

export function flowEdge(points, label = '', options = {}) {
  const pointString = points.map(([x, y]) => `${x},${y}`).join(' ');
  const marker = options.noArrow ? '' : ' marker-end="url(#arrow)"';
  const dash = options.dashed ? ' stroke-dasharray="8 6"' : '';
  let output = `<polyline points="${pointString}" fill="none" stroke="${options.stroke ?? '#111'}" stroke-width="${options.strokeWidth ?? 2.2}"${dash}${marker}/>`;
  if (!label) return `<g>${output}</g>`;

  let longest = -1;
  let labelAt = points[0];
  let labelSegment = [points[0], points[0]];
  for (let index = 1; index < points.length; index += 1) {
    const [x1, y1] = points[index - 1];
    const [x2, y2] = points[index];
    const length = Math.abs(x2 - x1) + Math.abs(y2 - y1);
    if (length > longest) {
      longest = length;
      labelAt = [(x1 + x2) / 2, (y1 + y2) / 2];
      labelSegment = [[x1, y1], [x2, y2]];
    }
  }
  const horizontal = Math.abs(labelSegment[1][0] - labelSegment[0][0]) >= Math.abs(labelSegment[1][1] - labelSegment[0][1]);
  const lines = String(label).split('\n');
  const size = options.labelSize ?? 13;
  const visualWidth = (line) => [...line].reduce((sum, char) => sum + (/^[\x00-\x7F]$/.test(char) ? size * 0.52 : size), 0);
  const width = Math.max(72, ...lines.map((line) => visualWidth(line) + 18));
  const lineHeight = Math.round(size * 1.3);
  const height = lines.length * lineHeight + 8;
  const defaultAt = horizontal
    ? [labelAt[0], labelAt[1] - height / 2 - 8]
    : [labelAt[0] + width / 2 + 10, labelAt[1]];
  const [labelX, labelY] = options.labelAt ?? defaultAt;
  const firstBaseline = labelY - (lines.length - 1) * lineHeight / 2 + size * 0.34;
  output += `<rect x="${labelX - width / 2}" y="${labelY - height / 2}" width="${width}" height="${height}" rx="3" fill="#fff" fill-opacity="0.94"/>`;
  output += textLines(labelX, firstBaseline, lines, { size, lineHeight, weight: 600 });
  return `<g>${output}</g>`;
}

export function region(x, y, w, h, title, options = {}) {
  const dashed = options.dashed ? ' stroke-dasharray="10 8"' : '';
  return `<g><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="8" fill="${options.fill ?? '#fbfbfb'}" stroke="${options.stroke ?? '#888'}" stroke-width="${options.strokeWidth ?? 1.4}"${dashed}/><rect x="${x}" y="${y}" width="${w}" height="40" rx="8" fill="#ededed"/><text x="${x + 16}" y="${y + 27}" font-size="17" font-weight="700">${escapeXml(title)}</text></g>`;
}

export function fileListCard(x, y, w, h, title, items, options = {}) {
  let output = `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="5" fill="#fff" stroke="#888" stroke-width="1.3"${options.dashed ? ' stroke-dasharray="8 6"' : ''}/>`;
  output += `<text x="${x + 14}" y="${y + 27}" font-size="16" font-weight="700">${escapeXml(title)}</text>`;
  let cursorY = y + 56;
  for (const item of items) {
    const [file, description] = item;
    output += `<text x="${x + 14}" y="${cursorY}" font-size="14" font-weight="700">${escapeXml(file)}</text>`;
    cursorY += 19;
    output += `<text x="${x + 14}" y="${cursorY}" font-size="12.8" fill="#333">${escapeXml(description)}</text>`;
    cursorY += 27;
  }
  return `<g>${output}</g>`;
}

export function page(title, subtitle, content, pageNumber, totalPages, footer = '当前实现：图内列明执行逻辑、对应文件与用途。') {
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${PAGE_WIDTH}" height="${PAGE_HEIGHT}" viewBox="0 0 ${PAGE_WIDTH} ${PAGE_HEIGHT}">
<defs>
  <marker id="arrow" markerWidth="12" markerHeight="12" refX="10" refY="4" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,8 L11,4 z" fill="#111"/></marker>
  <style>text{font-family:"Noto Sans CJK SC","Microsoft YaHei","PingFang SC",Arial,sans-serif;letter-spacing:0}</style>
</defs>
<rect width="${PAGE_WIDTH}" height="${PAGE_HEIGHT}" fill="#fff"/>
<text x="42" y="55" font-size="30" font-weight="800">${escapeXml(title)}</text>
<text x="42" y="91" font-size="17" fill="#333">${escapeXml(subtitle)}</text>
<line x1="42" y1="112" x2="2358" y2="112" stroke="#111" stroke-width="2"/>
${content}
<line x1="42" y1="1660" x2="2358" y2="1660" stroke="#aaa" stroke-width="1"/>
<text x="42" y="1682" font-size="12.5" fill="#555">${escapeXml(footer)}</text>
<text x="2358" y="1682" text-anchor="end" font-size="12.5" fill="#555">${pageNumber} / ${totalPages}</text>
</svg>`;
}


export function wrap(value,width,size=18) {
  const result=[];
  for(const paragraph of String(value??'').split('\n')){
    let line='',used=0;
    for(const ch of paragraph){
      const advance=/[\x00-\x7f]/.test(ch)?size*.6:size;
      if(used+advance>width&&line){
        if('，。；：！？、）】》'.includes(ch)){line+=ch;result.push(line);line='';used=0;continue;}
        result.push(line);line='';used=0;
      }
      line+=ch;used+=advance;
    }
    result.push(line);
  }
  return result;
}
export function text(x,y,value,width,size=20,color='#222',weight=400){
  const lines=Array.isArray(value)?value:wrap(value,width,size);
  return {height:lines.length*size*1.4,svg:textLines(x,y,lines,{size,lineHeight:size*1.4,anchor:'start',fill:color,weight})};
}
export function fitNode(type,w,h,title,lines,options={}){
  const ratio=type==='decision'?.6:1;
  const safeW=type==='decision'?w*.6:w-(type==='io'?72:40);
  const safeH=type==='decision'?h*.4:h-(type==='store'?65:36);
  for(let bodySize=options.bodySize||20;bodySize>=12;bodySize-=.5){
    const titleSize=bodySize+3,lineHeight=bodySize*1.3;
    const titleLines=wrap(title,safeW,titleSize);
    const bodyLines=lines.flatMap(v=>wrap(v,safeW,bodySize));
    const blockHeight=(titleLines.length+bodyLines.length)*lineHeight+(bodyLines.length?10:0);
    if(blockHeight<=safeH)return {titleLines,bodyLines,titleSize,bodySize,lineHeight,blockHeight};
  }
  throw Error('节点内容无法排入图形，请扩大此节点：'+title);
}
function overlap(a,b){return a.x<b.x+b.w&&a.x+a.w>b.x&&a.y<b.y+b.h&&a.y+a.h>b.y;}
function segmentHits(a,b,r){
  // Liang-Barsky with a slight inset: touching the frame is not crossing it.
  const min=[r.x+2,r.y+2],max=[r.x+r.w-2,r.y+r.h-2];let lo=0,hi=1;
  for(let k=0;k<2;k++){
    const delta=b[k]-a[k];
    if(Math.abs(delta)<1e-9){if(a[k]<=min[k]||a[k]>=max[k])return false;}
    else{let t1=(min[k]-a[k])/delta,t2=(max[k]-a[k])/delta;if(t1>t2)[t1,t2]=[t2,t1];lo=Math.max(lo,t1);hi=Math.min(hi,t2);if(lo>=hi)return false;}
  }
  return hi>0&&lo<1;
}
export function diagram(d){
  let svg='',warnings=[],bounds=[],labels=[];
  const cross=(a,b)=>a[0]*b[1]-a[1]*b[0];
  const sub=(a,b)=>[a[0]-b[0],a[1]-b[1]];
  const allEdges=d.edges||[];
  for(let i=0;i<allEdges.length;i++)for(let j=i+1;j<allEdges.length;j++){
    const a=allEdges[i],b=allEdges[j];let reported=false;
    for(let p=1;p<a.points.length&&!reported;p++)for(let q=1;q<b.points.length&&!reported;q++){
      const x=a.points[p-1],y=b.points[q-1],u=sub(a.points[p],x),v=sub(b.points[q],y),den=cross(u,v);
      if(Math.abs(den)<1e-8)continue;
      const t=cross(sub(y,x),v)/den,s=cross(sub(y,x),u)/den;
      if(t>1e-6&&t<1-1e-6&&s>1e-6&&s<1-1e-6){warnings.push('连线交叉：'+a.from+' → '+a.to+' / '+b.from+' → '+b.to+' @ '+Math.round(x[0]+t*u[0])+','+Math.round(x[1]+t*u[1]));reported=true;}
    }
  }
  const nodes=d.nodes.map(n=>({...n}));
  const byId=new Map(nodes.map(n=>[n.id,n]));
  const segments=(d.edges||[]).flatMap(e=>(e.points||[]).slice(1).map((q,i)=>({p:e.points[i],q})));
  for(const e of d.edges||[]){
    if(!byId.has(e.from)||!byId.has(e.to)||!e.points?.length)throw Error('无效边端点：'+e.from+' -> '+e.to);
    const points=e.points;
    for(let i=1;i<points.length;i++)for(const n of nodes)if(n.id!==e.from&&n.id!==e.to&&segmentHits(points[i-1],points[i],n))warnings.push('连线穿框：'+e.from+' -> '+e.to+' / '+n.id);
    let labelAt=e.labelAt,labelSize=18;
    if(e.label&&!labelAt){
      const pairs=points.slice(1).map((q,i)=>({p:points[i],q,length:Math.hypot(q[0]-points[i][0],q[1]-points[i][1])})).sort((a,b)=>b.length-a.length);
      search:for(const size of [18,16]){
        const width=Math.max(72,[...e.label].reduce((n,ch)=>n+(/[\x00-\x7f]/.test(ch)?size*.52:size),0)+18),height=Math.round(size*1.3)+8;
        for(const pair of pairs)for(const t of [.5,.3,.7])for(const offset of [12,32,60]){
          const mx=pair.p[0]+(pair.q[0]-pair.p[0])*t,my=pair.p[1]+(pair.q[1]-pair.p[1])*t;
          const horizontal=Math.abs(pair.q[0]-pair.p[0])>=Math.abs(pair.q[1]-pair.p[1]);
          const candidates=horizontal?[[mx,my-height/2-offset],[mx,my+height/2+offset]]:[[mx+width/2+offset,my],[mx-width/2-offset,my]];
          for(const [x,y]of candidates){
            const box={x:x-width/2,y:y-height/2,w:width,h:height};
            if(box.x<42||box.x+width>2358||box.y<180||box.y+height>1640)continue;
            if(nodes.some(n=>overlap(box,n))||labels.some(n=>overlap(box,n))||segments.some(s=>segmentHits(s.p,s.q,box)))continue;
            labelAt=[x,y];labelSize=size;labels.push(box);break search;
          }
        }
      }
      if(!labelAt)warnings.push('标签需要调整：'+e.from+' -> '+e.to);
    }
    svg+=flowEdge(points,e.label||'',{labelSize,labelAt});
  }
  for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++)if(overlap(nodes[i],nodes[j]))warnings.push('节点重叠：'+nodes[i].id+' / '+nodes[j].id);
  for(const n of nodes){
    if(![n.x,n.y,n.w,n.h].every(Number.isFinite))throw Error('节点坐标无效：'+n.id);
    if(n.x<42||n.y<175||n.x+n.w>2358||n.y+n.h>1630)warnings.push('节点超出页面：'+n.id);
    const files=n.files||[],lines=[...(n.lines||[])];
    if(n.criteria?.length)lines.push(...n.criteria);
    if(files.length&&lines.length)lines.push('');
    const secondaryFrom=files.length?lines.length:undefined;
    for(const f of files)lines.push(f.path+'：'+f.purpose);
    if(n.detailRef)lines.push(n.detailLabel||('逻辑展开：'+n.detailRef));
    const layout=fitNode(n.type,n.w,n.h,n.title,lines,{bodySize:n.bodySize||20});
    bounds.push({id:n.id,x:n.x,y:n.y,w:n.w,h:n.h,bodySize:layout.bodySize,lines:layout.bodyLines.length,files:files.map(f=>f.path)});
    if(layout.bodySize<16)warnings.push('建议增大字号：'+n.id+' / '+layout.bodySize);
    svg+=flowNode(n.type,n.x,n.y,n.w,n.h,n.title,lines,{bodySize:n.bodySize||20,secondaryFrom,fill:n.detailRef?'#eff6ff':undefined,stroke:n.detailColor||undefined,strokeWidth:n.detailRef?4:2});
  }
  return {svg,bounds,warnings};
}
