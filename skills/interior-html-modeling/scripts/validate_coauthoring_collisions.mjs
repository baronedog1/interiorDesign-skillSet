#!/usr/bin/env node
import { spawn } from 'node:child_process';
import fs from 'node:fs/promises';
import net from 'node:net';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const [htmlPath, outputDir] = process.argv.slice(2);
if (!htmlPath || !outputDir) throw new Error('usage: validate_coauthoring_collisions.mjs <standalone-html> <output-dir>');
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const freePort = async () => {
  const server = net.createServer();
  await new Promise((resolve, reject) => server.listen(0, '127.0.0.1', resolve).once('error', reject));
  const port = server.address().port;
  await new Promise((resolve) => server.close(resolve));
  return port;
};

await fs.mkdir(outputDir, { recursive: true });
const port = await freePort();
const chrome = spawn(process.env.CHROME_BIN || '/home/agentops/agent-runtime/bin/render-chrome', [
  '--headless=new', '--no-sandbox', '--disable-dev-shm-usage',
  '--remote-debugging-address=127.0.0.1', `--remote-debugging-port=${port}`,
  `--user-data-dir=${path.join(outputDir, '.profile')}`, '--window-size=1920,1080',
  '--use-gl=angle', '--use-angle=swiftshader', '--enable-webgl', '--enable-unsafe-swiftshader',
  '--allow-file-access-from-files', '--ignore-gpu-blocklist', '--hide-scrollbars',
  '--disable-background-networking', '--disable-component-update', '--disable-sync', '--disable-default-apps',
  '--disable-extensions', '--no-first-run', '--no-default-browser-check', 'about:blank',
], { stdio: ['ignore', 'ignore', 'pipe'], detached: true });

let stderr = '';
chrome.stderr.on('data', (chunk) => { stderr = `${stderr}${chunk}`.slice(-12000); });
let socket;
try {
  let version;
  for (let i = 0; i < 300 && !version; i += 1) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json/version`);
      if (response.ok) version = await response.json();
    } catch {}
    if (!version) await sleep(100);
  }
  if (!version) throw new Error(`Chrome did not start: ${stderr.slice(-1200)}`);
  const target = await (await fetch(`http://127.0.0.1:${port}/json/new?about%3Ablank`, { method: 'PUT' })).json();
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, { once: true });
    socket.addEventListener('error', reject, { once: true });
  });
  let sequence = 0;
  const pending = new Map();
  const consoleErrors = [];
  const consoleWarnings = [];
  socket.addEventListener('message', (event) => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      const entry = pending.get(message.id);
      pending.delete(message.id);
      message.error ? entry.reject(new Error(message.error.message)) : entry.resolve(message.result);
      return;
    }
    if (message.method === 'Runtime.exceptionThrown') consoleErrors.push(message.params.exceptionDetails?.exception?.description || message.params.exceptionDetails?.text);
    if (message.method === 'Runtime.consoleAPICalled') {
      const text = message.params.args.map((item) => item.value || item.description || '').join(' ');
      if (message.params.type === 'error') consoleErrors.push(text);
      if (message.params.type === 'warning') consoleWarnings.push(text);
    }
  });
  const send = (method, params = {}) => {
    const id = ++sequence;
    socket.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
  };
  const evaluate = async (expression) => {
    const response = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
    if (response.exceptionDetails) throw new Error(response.exceptionDetails.exception?.description || response.exceptionDetails.text);
    return response.result.value;
  };
  const drag = async (from, to, steps = 28, captureName = null) => {
    await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: from.x, y: from.y });
    await send('Input.dispatchMouseEvent', { type: 'mousePressed', x: from.x, y: from.y, button: 'left', clickCount: 1 });
    for (let i = 1; i <= steps; i += 1) {
      const t = i / steps;
      await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: from.x + (to.x - from.x) * t, y: from.y + (to.y - from.y) * t, button: 'left', buttons: 1 });
      await sleep(14);
    }
    if (captureName) {
      const captured = await send('Page.captureScreenshot', { format: 'png', fromSurface: true });
      await fs.writeFile(path.join(outputDir, captureName), Buffer.from(captured.data, 'base64'));
    }
    await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: to.x, y: to.y, button: 'left', clickCount: 1 });
    await sleep(250);
  };

  await send('Page.enable');
  await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url: pathToFileURL(path.resolve(htmlPath)).href });
  for (let i = 0; i < 900 && !(await evaluate('Boolean(window.__INTERIOR_COAUTHORING_BOOT__?.ready && window.__INTERIOR_COAUTHORING_EDITOR__)')); i += 1) await sleep(100);
  if (!(await evaluate('Boolean(window.__INTERIOR_COAUTHORING_BOOT__?.ready && window.__INTERIOR_COAUTHORING_EDITOR__)'))) {
    const bootState = await evaluate('({boot:window.__INTERIOR_COAUTHORING_BOOT__||null,hasEditor:Boolean(window.__INTERIOR_COAUTHORING_EDITOR__)})');
    throw new Error(`coauthoring editor did not become ready within 90 seconds: ${JSON.stringify(bootState)}; console=${JSON.stringify(consoleErrors)}`);
  }
  for (let i = 0; i < 900 && !(await evaluate('Boolean(window.__INTERIOR_MANAGED_COMPONENT_STATE__?.ready)')); i += 1) await sleep(100);
  if (!(await evaluate('Boolean(window.__INTERIOR_MANAGED_COMPONENT_STATE__?.ready)'))) throw new Error('managed component state did not become ready within 90 seconds');
  await sleep(600);

  const initial = await evaluate(`(() => {
    const api=window.__INTERIOR_COAUTHORING_EDITOR__, m=api.model;
    const structureButtons=[...document.querySelectorAll('[data-domain-tools="structure"] .structure-icon-grid button')];
    document.querySelector('[data-domain="layers"]').click();const ceilingLayer=Boolean(document.querySelector('[data-layer="ceiling"]')),pendantLayer=Boolean(document.querySelector('[data-layer="pendants"]'));document.querySelector('[data-domain="structure"]').click();
    const saveButton=document.querySelector('#exportBtn');
    const saveReturnNote=document.querySelector('.save-return-note');
    return {version:api.version,boot:window.__INTERIOR_COAUTHORING_BOOT__,walls:m.walls.length,openings:m.openings.length,furniture:m.furniture.length,initialAudit:api.collisionAudit(),cabinetAudit:api.cabinetCollisionAudit(),normalization:api.normalization,rich:JSON.parse(JSON.stringify(window.__INTERIOR_MANAGED_COMPONENT_STATE__)),ui:{structureIconCount:structureButtons.length,allStructureButtonsSvgOnly:structureButtons.every(b=>b.querySelector('svg')&&!b.textContent.trim()),allStructureButtonsHaveTooltip:structureButtons.every(b=>b.dataset.tooltip&&b.getAttribute('aria-label')),componentDeleteTop:Boolean(document.querySelector('[data-domain-tools="component"] #deleteComponentBtn')),componentDeleteInInspector:Boolean(document.querySelector('#properties [data-action="delete"]')),ceilingLayer,pendantLayer,saveCurrentHtmlButton:Boolean(saveButton&&/保存新版HTML/.test(saveButton.textContent)),saveReturnNote:Boolean(saveReturnNote&&/发回|回传|发送/.test(saveReturnNote.textContent)),algorithmicCameraBridge:['setAlgorithmicCaptureMode','setAlgorithmicCamera','getAlgorithmicFrameFacts'].every(name=>typeof api[name]==='function')}};
  })()`);

  await send('Page.setDownloadBehavior', { behavior: 'allow', downloadPath: path.resolve(outputDir) });
  await evaluate('document.querySelector("#exportBtn").click();true');
  let savedHtmlName = null;
  for (let i = 0; i < 240 && !savedHtmlName; i += 1) {
    const names = await fs.readdir(outputDir);
    savedHtmlName = names.find((name) => name.endsWith('.html') && !name.endsWith('.crdownload')) || null;
    if (!savedHtmlName) await sleep(100);
  }
  let savedReturnHtml = { exists: false };
  if (savedHtmlName) {
    const savedText = await fs.readFile(path.join(outputDir, savedHtmlName), 'utf8');
    const modelMatch = savedText.match(/<script\b[^>]*\bid=["']template-data["'][^>]*>([\s\S]*?)<\/script>/i);
    const savedModel = modelMatch ? JSON.parse(modelMatch[1]) : null;
    savedReturnHtml = {
      exists: true,
      fileName: savedHtmlName,
      bytes: Buffer.byteLength(savedText),
      documentRole: savedModel?.meta?.documentRole || null,
      editorVersion: savedModel?.meta?.coauthoringEditorVersion || null,
      walls: savedModel?.walls?.length ?? null,
      openings: savedModel?.openings?.length ?? null,
      furniture: savedModel?.furniture?.length ?? null,
    };
  }

  const deterministic = await evaluate(`(() => {
    const api=window.__INTERIOR_COAUTHORING_EDITOR__, m=api.model;
    const movable=m.furniture.filter(f=>f.semantic==='movable-green' && Number(f.height||0)>.08);
    const furnitureOverlap={...movable[1],id:'fixture-furniture-overlap',x:movable[0].x,z:movable[0].z,y:movable[0].y};
    const furnitureOutside={...movable[0],id:'fixture-furniture-outside',x:-100,z:-100};
    const openingOverlap={...m.openings[0],id:'fixture-opening-overlap'};
    const base=m.walls.find(w=>Math.hypot(w.b.x-w.a.x,w.b.z-w.a.z)>.8);
    const collinear={...structuredClone(base),id:'fixture-wall-collinear'};
    let perpendicular=null,oblique=null;
    for(const w of m.walls){
      const dx=w.b.x-w.a.x,dz=w.b.z-w.a.z,L=Math.hypot(dx,dz);if(L<.8)continue;
      const ux=dx/L,uz=dz/L,mx=(w.a.x+w.b.x)/2,mz=(w.a.z+w.b.z)/2;
      const p={id:'fixture-wall-perpendicular',name:'垂直测试墙',a:{x:mx-uz*.32,z:mz+ux*.32},b:{x:mx+uz*.32,z:mz-ux*.32},thickness:.08,height:2.8};
      if(!api.validateWall(p)){perpendicular=p;const a=.62,c=Math.cos(a),s=Math.sin(a),vx=(-uz*c-ux*s)*.32,vz=(ux*c-uz*s)*.32;oblique={id:'fixture-wall-oblique',name:'斜交测试墙',a:{x:mx-vx,z:mz-vz},b:{x:mx+vx,z:mz+vz},thickness:.08,height:2.8};break}
    }
    const cabinet=m.furniture.find(f=>f.semantic==='fixed-purple');const cabinetTooTall={...structuredClone(cabinet),height:99};
    return {furnitureOverlap:api.validateFurniture(furnitureOverlap),furnitureOutside:api.validateFurniture(furnitureOutside),cabinetTooTall:api.validateFurniture(cabinetTooTall),openingOverlap:api.validateOpening(openingOverlap),wallCollinear:api.validateWall(collinear),wallPerpendicular:perpendicular?api.validateWall(perpendicular):'no-fixture',wallOblique:oblique?api.validateWall(oblique):'no-fixture',perpendicular,oblique};
  })()`);

  await evaluate('window.__INTERIOR_COAUTHORING_EDITOR__.switchView("plan");window.__INTERIOR_COAUTHORING_EDITOR__.fitView();true');
  await sleep(250);
  const furnitureDragBefore = await evaluate(`(() => {
    const api=window.__INTERIOR_COAUTHORING_EDITOR__,m=api.model,items=m.furniture.filter(f=>f.semantic==='movable-green'&&Number(f.height||0)>.08),moving=items[0],target=items[1];
    api.select('furniture',moving.id,true);
    return {movingId:moving.id,targetId:target.id,before:{x:moving.x,z:moving.z},from:api.handleScreen('furniture-position'),to:api.project({x:target.x,y:0,z:target.z})};
  })()`);
  await drag(furnitureDragBefore.from, furnitureDragBefore.to, 34, '家具碰撞阻挡验收.png');
  const furnitureDragAfter = await evaluate(`(() => {const api=window.__INTERIOR_COAUTHORING_EDITOR__,f=api.model.furniture.find(x=>x.id===${JSON.stringify(furnitureDragBefore.movingId)});return {after:{x:f.x,z:f.z},valid:api.validateFurniture(f),diagnostics:JSON.parse(JSON.stringify(window.__INTERIOR_COLLISION_DIAGNOSTICS__))}})()`);

  const openingDragBefore = await evaluate(`(() => {const api=window.__INTERIOR_COAUTHORING_EDITOR__,o=api.model.openings[0],w=api.model.walls.find(x=>x.id===o.wallId);api.select('opening',o.id,true);return {id:o.id,wallId:w.id,wallLength:Math.hypot(w.b.x-w.a.x,w.b.z-w.a.z),width:o.width,from:api.handleScreen('opening-center'),to:api.wallPoint(w.id,Math.hypot(w.b.x-w.a.x,w.b.z-w.a.z)+2,(o.bottom+o.height/2))};})()`);
  await drag(openingDragBefore.from, openingDragBefore.to, 30);
  const openingDragAfter = await evaluate(`(() => {const api=window.__INTERIOR_COAUTHORING_EDITOR__,o=api.model.openings.find(x=>x.id===${JSON.stringify(openingDragBefore.id)});return {opening:o,valid:api.validateOpening(o)}})()`);

  const scaleBefore = await evaluate(`(() => {const api=window.__INTERIOR_COAUTHORING_EDITOR__,f=api.model.furniture.find(x=>x.semantic==='movable-green'&&Number(x.height||0)>.2);api.select('furniture',f.id,true);const from=api.handleScreen('furniture-scale-se'),opposite=api.handleScreen('furniture-scale-nw');return {id:f.id,width:f.width,depth:f.depth,height:f.height,from,to:{x:from.x*.78+opposite.x*.22,y:from.y*.78+opposite.y*.22}}})()`);
  await drag(scaleBefore.from, scaleBefore.to, 30, '组件等比例缩放与顶部工具栏验收.png');
  const scaleAfter = await evaluate(`(() => {const api=window.__INTERIOR_COAUTHORING_EDITOR__,f=api.model.furniture.find(x=>x.id===${JSON.stringify(scaleBefore.id)}),deleteButton=document.querySelector('#deleteComponentBtn');return {width:f.width,depth:f.depth,height:f.height,widthFactor:f.width/${scaleBefore.width},depthFactor:f.depth/${scaleBefore.depth},heightFactor:f.height/${scaleBefore.height},deleteButtonEnabled:Boolean(deleteButton&&!deleteButton.disabled),inspectorDeleteExists:Boolean(document.querySelector('#properties [data-action="delete"]')),valid:api.validateFurniture(f)}})()`);

  const wallThickness = await evaluate(`(() => {const api=window.__INTERIOR_COAUTHORING_EDITOR__,w=api.model.walls.find(x=>Number(x.thickness)>.05);api.select('wall',w.id,true);const input=document.querySelector('#selectionQuickActions #quickWallThickness'),before=w.thickness,next=Math.max(.04,Number(before)-.01);input.value=next;input.dispatchEvent(new Event('change',{bubbles:true}));const after=api.model.walls.find(x=>x.id===w.id).thickness;return {id:w.id,before,after,inputAtTop:Boolean(input),duplicateThicknessInputs:document.querySelectorAll('[data-field="thickness"]').length}})()`);

  const layers = await evaluate(`(() => {document.querySelector('[data-domain="layers"]').click();const ceiling=document.querySelector('[data-layer="ceiling"]'),pendants=document.querySelector('[data-layer="pendants"]');ceiling.checked=true;ceiling.dispatchEvent(new Event('change',{bubbles:true}));pendants.checked=false;pendants.dispatchEvent(new Event('change',{bubbles:true}));return {ceiling:Boolean(window.__INTERIOR_COAUTHORING_EDITOR__.state.layers.ceiling),pendants:Boolean(window.__INTERIOR_COAUTHORING_EDITOR__.state.layers.pendants),ceilingControl:Boolean(ceiling),pendantControl:Boolean(pendants)}})()`);

  const result = {
    ok: initial.version === '1.4.0'
      && initial.boot?.ready === true
      && initial.ui.structureIconCount === 6
      && initial.ui.allStructureButtonsSvgOnly === true
      && initial.ui.allStructureButtonsHaveTooltip === true
      && initial.ui.componentDeleteTop === true
      && initial.ui.saveCurrentHtmlButton === true
      && initial.ui.saveReturnNote === true
      && initial.ui.algorithmicCameraBridge === true
      && savedReturnHtml.exists === true
      && savedReturnHtml.documentRole === 'user-returned-current-html'
      && savedReturnHtml.editorVersion === '1.4.0'
      && savedReturnHtml.walls === initial.walls
      && savedReturnHtml.openings === initial.openings
      && savedReturnHtml.furniture === initial.furniture
      && initial.ui.ceilingLayer === true
      && initial.ui.pendantLayer === true
      && initial.cabinetAudit.length === 0
      && initial.normalization.completed === true
      && initial.rich.ready === true
      && initial.rich.rendered === initial.rich.matched
      && initial.rich.failed === 0
      && initial.rich.authoredMeshCount > 0
      && deterministic.furnitureOverlap?.kind === 'furniture'
      && deterministic.furnitureOutside?.kind === 'boundary'
      && deterministic.cabinetTooTall?.kind === 'ceiling'
      && deterministic.openingOverlap?.kind === 'opening'
      && deterministic.wallCollinear?.kind === 'wall-collinear'
      && deterministic.wallPerpendicular === null
      && deterministic.wallOblique?.kind === 'wall-angle'
      && furnitureDragAfter.valid === null
      && (Math.abs(furnitureDragAfter.after.x - furnitureDragBefore.to.x) > 0 || furnitureDragAfter.diagnostics.blockedAttempts > 0)
      && furnitureDragAfter.diagnostics.blockedAttempts > 0
      && openingDragAfter.valid === null
      && openingDragAfter.opening.center + openingDragAfter.opening.width / 2 <= openingDragBefore.wallLength - .05 + .02
      && scaleAfter.width < scaleBefore.width
      && Math.abs(scaleAfter.widthFactor-scaleAfter.depthFactor) < .02
      && Math.abs(scaleAfter.widthFactor-scaleAfter.heightFactor) < .02
      && scaleAfter.deleteButtonEnabled === true
      && scaleAfter.inspectorDeleteExists === false
      && scaleAfter.valid === null
      && wallThickness.inputAtTop === true
      && wallThickness.duplicateThicknessInputs === 1
      && wallThickness.after < wallThickness.before
      && layers.ceiling === true
      && layers.pendants === false
      && consoleErrors.length === 0,
    initial,
    savedReturnHtml,
    deterministic,
    realPointer: { furniture: { before: furnitureDragBefore, after: furnitureDragAfter }, opening: { before: openingDragBefore, after: openingDragAfter }, scale: { before: scaleBefore, after: scaleAfter } },
    wallThickness,
    layers,
    consoleErrors,
    consoleWarnings,
    chrome: { product: version.Browser, stderrTail: stderr.slice(-3000) },
  };
  await fs.writeFile(path.join(outputDir, 'collision-acceptance.json'), `${JSON.stringify(result, null, 2)}\n`);
  console.log(JSON.stringify(result, null, 2));
  if (!result.ok) process.exitCode = 1;
} catch (error) {
  const detail = error instanceof Error ? `${error.stack || error.message}\n\nChrome stderr:\n${stderr}` : String(error);
  await fs.writeFile(path.join(outputDir, 'browser-error.txt'), detail);
  console.error(detail);
  process.exitCode = 1;
} finally {
  try { socket?.close(); } catch {}
  try { process.kill(-chrome.pid, 'SIGTERM'); } catch { try { chrome.kill('SIGTERM'); } catch {} }
}
