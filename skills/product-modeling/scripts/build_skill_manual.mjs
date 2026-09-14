#!/usr/bin/env node
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {page,text,diagram} from './flowchart-layout.mjs';

export function run(command,args) {
  const r=spawnSync(command,args,{encoding:'utf8',maxBuffer:20*1024*1024});
  if(r.status!==0)throw Error(command+': '+(r.error?.message||r.stderr||r.stdout));
  return r.stdout;
}
export function actualFiles(root) {
  const out=[],skip=new Set(['.git','node_modules','__pycache__','.runtime']);
  function walk(dir) {for(const e of fs.readdirSync(dir,{withFileTypes:true})) {
    if(skip.has(e.name)||e.name.endsWith('.pyc'))continue;
    const p=path.join(dir,e.name);
    if(e.isSymbolicLink())throw Error('请先核实包内链接：'+p);
    if(e.isDirectory())walk(p);else out.push(path.relative(root,p).split(path.sep).join('/'));
  }}
  walk(root);return out.sort();
}
export function renderManual(root) {
  const skill=fs.readFileSync(path.join(root,'SKILL.md'),'utf8');
  const yaml=skill.match(/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/)?.[0]?.trim();
  if(!yaml)throw Error('缺少Skill入口说明');
  const spec=JSON.parse(fs.readFileSync(path.join(root,'manual/skill-manual.json'),'utf8'));
  if(spec.schemaVersion!==5||spec.overview)throw Error('请按schemaVersion 5重构完整主线，不保留重复overview');
  if(!spec.displayName||!spec.version||!spec.scenarios?.length)throw Error('缺少说明书身份或主流程');
  const files=[...new Set([...actualFiles(root),'SKILL_MANUAL.pdf','manual/skill-manual.md','manual/skill-flowchart.svg'])].sort();
  if(JSON.stringify(Object.keys(spec.fileDescriptions||{}).sort())!==JSON.stringify(files)||Object.values(spec.fileDescriptions).some(v=>typeof v!=='string'||!v.trim()))throw Error('文件用途清单与实际包不一致');
  const covered=new Set(),mains=new Set(),entries=[],details=new Map();
  for(const d of spec.logicDetails||[]) {
    if(!d.id||details.has(d.id)||!d.code||!d.explanation||!d.returnTo||d.diagrams?.length!==1)throw Error('节点展开缺少身份、解释、返回位置或包含多条图');
    details.set(d.id,d);
  }
  function checkGraph(d) {
    if(!d?.title||!d.nodes?.length)throw Error('空流程图');
    const nodes=new Map();
    for(const n of d.nodes) {
      if(!n.id||nodes.has(n.id)||!n.title)throw Error('节点身份重复或缺失');
      if(!n.files?.length)throw Error('节点没有真实文件支撑：'+n.id);
      for(const f of n.files) {
        if(!f.purpose?.trim())throw Error('文件缺少具体用途：'+f.path);
        if(files.includes(f.path))covered.add(f.path);
        else if(!(spec.dependencyFiles||[]).some(x=>x.path===f.path)||!fs.statSync(path.resolve(root,f.path)).isFile())throw Error('引用的文件不存在：'+f.path);
      }
      if(n.check===true&&n.type!=='decision')throw Error('改变去向的判断应为菱形：'+n.id);
      nodes.set(n.id,n);
    }
    if(!nodes.has(d.startNode)||!d.endNodes?.length||d.endNodes.some(x=>!nodes.has(x)))throw Error('主线缺少明确起点或终点');
    for(const e of d.edges||[])if(!nodes.has(e.from)||!nodes.has(e.to))throw Error('连线引用了不存在的节点');
    for(const n of nodes.values())if(n.type==='decision') {
      const out=d.edges.filter(e=>e.from===n.id);
      if(out.length<2||out.some(e=>!e.label?.trim()))throw Error('判断缺少明确结果去向：'+n.id);
    }
    function visit(starts,reverse=false) {
      const seen=new Set(starts),queue=[...starts];
      while(queue.length) {
        const at=queue.shift();
        for(const e of d.edges||[])if((reverse?e.to:e.from)===at) {
          const to=reverse?e.from:e.to;if(!seen.has(to)){seen.add(to);queue.push(to);}
        }
      }
      return seen;
    }
    if(visit([d.startNode]).size!==nodes.size||visit(d.endNodes,true).size!==nodes.size)throw Error('存在未接入起点或无法到达终点的节点');
    return nodes;
  }
  for(const s of spec.scenarios) {
    if(!s.id||mains.has(s.id)||!s.trigger||!s.input||!s.output||!s.explanation||s.diagrams?.length!==1)throw Error('每个场景必须只有一张从触发到交付的总图');
    if(spec.scenarios.length>1&&!s.independenceReason)throw Error('多个总流程必须说明独立触发与目的');
    mains.add(s.id);const d=s.diagrams[0],nodes=checkGraph(d);
    entries.push({s,d,kind:'总流程'});
    for(const n of d.nodes)if(n.detailRef) {
      const detail=details.get(n.detailRef);
      if(!detail||detail.parent)throw Error('展开必须唯一对应主图节点：'+n.id);
      if(!nodes.has(detail.returnTo))throw Error('展开接回位置不在所属主流程');
      detail.parent={scenario:s.id,node:n.id,title:n.title,returnTitle:nodes.get(detail.returnTo).title};
      checkGraph(detail.diagrams[0]);
    }
  }
  for(const d of details.values()) {
    if(!d.parent)throw Error('展开页没有主节点');
    if(d.diagrams[0].nodes.some(n=>n.detailRef))throw Error('不要嵌套展开页，回到主流程整理');
    entries.push({s:d,d:d.diagrams[0],kind:'节点展开'});
  }
  const missing=files.filter(f=>!covered.has(f));
  if(missing.length)throw Error('文件没有对应流程节点：'+missing.join('、'));
  const pageIndex=new Map(entries.map((e,i)=>[e.s.id,i+1]));
  const pages=[],metrics=[],md=['# '+spec.displayName+' 说明书','','版本：'+spec.version,'','~~~yaml',yaml,'~~~'];
  for(const [i,e] of entries.entries()) {
    const parent=e.s.parent;
    const intro=parent?'展开「'+parent.title+'」；完成后接回「'+parent.returnTitle+'」，不是另一次调用。':'触发：'+e.s.trigger+'；输入：'+e.s.input+'；交付：'+e.s.output;
    const t=text(60,145,intro,2280,21);
    if(t.height>65)throw Error('流程说明过长，请精简到输入和最终结果');
    const linked={...e.d,nodes:e.d.nodes.map(n=>{
      const d=details.get(n.detailRef);
      return d?{...n,detailLabel:d.code+' · '+d.title+' · 第'+pageIndex.get(d.id)+'页',detailColor:d.color||'#246f9a'}:n;
    })};
    const result=diagram(linked);
    pages.push(page(spec.displayName+' / '+e.kind+'：'+e.d.title,'版本 '+spec.version+' · '+(parent?'第'+pageIndex.get(parent.scenario)+'页主节点展开':'从接任务到交付，沿箭头阅读'),t.svg+result.svg,i+1,entries.length));
    metrics.push({title:e.d.title,...result,svg:undefined});
    md.push('','## '+e.kind+'：'+e.d.title,'',intro,e.s.explanation);
    for(const n of linked.nodes) {
      md.push('- '+n.title+'：'+(n.lines||[]).join('；')+(n.detailLabel?'；'+n.detailLabel:''));
      for(const f of n.files)md.push('  - '+f.path+'：'+f.purpose);
    }
    for(const edge of e.d.edges)md.push('- '+edge.from+' → '+edge.to+(edge.label?'：'+edge.label:''));
  }
  md.push('','## 文件索引（用途已在流程中对应）');
  for(const f of files)md.push('- '+f+'：'+spec.fileDescriptions[f]);
  return {pages,overview:pages[0],markdown:md.join('\n')+'\n',files,metrics,spec};
}
export function build(root,evidenceDir) {
  const result=renderManual(root),temp=fs.mkdtempSync(path.join(os.tmpdir(),'skill-manual-'));
  try {
    const pdfs=[];
    result.pages.forEach((svg,i)=>{
      const sp=path.join(temp,'page-'+String(i+1).padStart(2,'0')+'.svg'),pp=sp.replace('.svg','.pdf');
      fs.writeFileSync(sp,svg);
      run('python3',['-m','cairosvg',sp,'--output-width','1587.4016','--output-height','1122.5197','-f','pdf','-o',pp]);pdfs.push(pp);
    });
    const pdf=path.join(temp,'manual.pdf');
    run('gs',['-q','-dSAFER','-dBATCH','-dNOPAUSE','-sDEVICE=pdfwrite','-sOutputFile='+pdf,...pdfs]);
    if(evidenceDir) {
      fs.mkdirSync(evidenceDir,{recursive:true});
      for(const f of fs.readdirSync(temp).filter(f=>f.endsWith('.svg')))fs.copyFileSync(path.join(temp,f),path.join(evidenceDir,f));
      run('gs',['-q','-dSAFER','-dBATCH','-dNOPAUSE','-sDEVICE=png16m','-r96','-sOutputFile='+path.join(evidenceDir,'page-%02d.png'),pdf]);
      fs.writeFileSync(path.join(evidenceDir,'layout.json'),JSON.stringify({pages:result.pages.length,diagrams:result.metrics},null,2));
    }
    for(const [f,data]of [['SKILL_MANUAL.pdf',fs.readFileSync(pdf)],['manual/skill-manual.md',result.markdown],['manual/skill-flowchart.svg',result.overview]]) {
      const target=path.join(root,f),staged=target+'.tmp';
      fs.writeFileSync(staged,data);fs.renameSync(staged,target);
    }
    return {ok:true,version:result.spec.version,files:result.files.length,pages:result.pages.length};
  } finally {fs.rmSync(temp,{recursive:true,force:true});}
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  const root=path.resolve(process.argv[2]||'.'),i=process.argv.indexOf('--evidence-dir');
  console.log(JSON.stringify(build(root,i>=0?path.resolve(process.argv[i+1]):undefined),null,2));
}
