#!/usr/bin/env node
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {renderManual,run} from './build_skill_manual.mjs';

const root=path.resolve(process.argv[2]||'.'),expected=renderManual(root);
for(const [file,value]of [['manual/skill-manual.md',expected.markdown],['manual/skill-flowchart.svg',expected.overview]]) {
  if(fs.readFileSync(path.join(root,file),'utf8')!==value)throw Error('Stale generated file: '+file);
}
const manifest=JSON.parse(fs.readFileSync(path.join(root,'MANIFEST.json'),'utf8'));
if(manifest.version!==expected.spec.version||manifest.file_count!==expected.files.length||JSON.stringify([...manifest.files].sort())!==JSON.stringify(expected.files))throw Error('MANIFEST mismatch');
const pdf=path.join(root,'SKILL_MANUAL.pdf'),temp=fs.mkdtempSync(path.join(os.tmpdir(),'manual-check-'));
const ps=value=>'('+value.replaceAll('\\','\\\\').replaceAll('(','\\(').replaceAll(')','\\)')+')';
try {
  const count=Number(run('gs',['-q','-dNODISPLAY','-dNOSAFER','-c',ps(pdf)+' (r) file runpdfbegin pdfpagecount = quit']));
  if(count!==expected.pages.length)throw Error('PDF page count mismatch');
  for(let i=1;i<=count;i++) {
    const box=run('gs',['-q','-dNODISPLAY','-dNOSAFER','-c',ps(pdf)+' (r) file runpdfbegin '+i+' pdfgetpage /MediaBox get == quit']);
    const a=(box.match(/[\d.]+/g)||[]).map(Number);
    if(Math.abs(a[2]-a[0]-1190.55)>.8||Math.abs(a[3]-a[1]-841.89)>.8)throw Error('Non-A3 page '+i);
  }
  run('gs',['-q','-dSAFER','-dBATCH','-dNOPAUSE','-sDEVICE=png16m','-r36','-sOutputFile='+path.join(temp,'actual-%02d.png'),pdf]);
  // Re-render source and compare pixels through the same independent PDF engine.
  // This catches stale PDFs even when page count and file lists have not changed.
  for(let i=0;i<expected.pages.length;i++) {
    const svg=path.join(temp,'expected.svg'),pagePdf=path.join(temp,'expected.pdf'),png=path.join(temp,'expected.png');
    fs.writeFileSync(svg,expected.pages[i]);
    run('python3',['-m','cairosvg',svg,'--output-width','1587.4016','--output-height','1122.5197','-f','pdf','-o',pagePdf]);
    run('gs',['-q','-dSAFER','-dBATCH','-dNOPAUSE','-sDEVICE=png16m','-r36','-sOutputFile='+png,pagePdf]);
    const actual=path.join(temp,'actual-'+String(i+1).padStart(2,'0')+'.png');
    run('python3',['-c','from PIL import Image,ImageChops,ImageStat; import sys; a=Image.open(sys.argv[1]).convert("RGB"); b=Image.open(sys.argv[2]).convert("RGB"); assert a.size==b.size; assert min(ImageStat.Stat(a).mean)<254,"Blank PDF page"; diff=ImageStat.Stat(ImageChops.difference(a,b)); assert max(diff.mean)<0.5,"Stale or altered PDF page"',actual,png]);
  }
  console.log(JSON.stringify({ok:true,version:expected.spec.version,scenarios:expected.spec.scenarios.length,files:expected.files.length,pages:count,a3Landscape:true,independentReopen:true,sourcePixelComparison:true,geometryChecked:true},null,2));
} finally {fs.rmSync(temp,{recursive:true,force:true});}
