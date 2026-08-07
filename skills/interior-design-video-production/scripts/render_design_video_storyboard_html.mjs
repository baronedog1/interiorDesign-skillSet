#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';

const args = process.argv.slice(2);
if (!args.length || args.includes('--help')) {
  console.log('Usage: node scripts/render_design_video_storyboard_html.mjs <video-storyboard-plan.json> --out preview.html');
  process.exit(args.includes('--help') ? 0 : 1);
}
const planPath = args[0];
const outIndex = args.indexOf('--out');
const outPath = outIndex >= 0 ? args[outIndex + 1] : path.join(process.cwd(), 'video-storyboard-preview.html');
const plan = JSON.parse(fs.readFileSync(planPath, 'utf8'));
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const imageMap = new Map((plan.images || []).map((image) => [image.id, image]));
const detailMap = new Map((plan.derivedDetailAssets || []).map((image) => [image.id, image]));
const resolveImage = (id) => imageMap.get(id) || detailMap.get(id) || { id, title: id, url: '', localPath: '' };
const shots = plan.shots || [];
const candidates = plan.aiCharacter?.candidates || plan.aiCharacter?.backupCandidates || [];
const globalRefs = plan.globalReferenceVideos || [];
const storyboard = plan.storyboardSketch || plan.storyboard || null;
const storyboardPanels = plan.storyboardPanels || storyboard?.panels || [];
const character = plan.aiCharacter || {};
const characterWardrobe = character.wardrobeNote || character.clothingDetail || character.outfitDetail || '';
const characterAppearance = character.appearancePrompt || character.description || character.displayLabel || '';
const characterPanel = character.enabled ? `<section class="panel character"><h2>主讲虚拟模特</h2><div class="character-grid"><div><p><strong>角色资产：</strong>${esc(character.sssid || character.assetId || '')}</p><p><strong>Asset URI：</strong>${esc(character.seedanceAssetUri || character.assetUri || '')}</p><p><strong>形象设定：</strong>${esc(characterAppearance)}</p><p><strong>穿着与衣服细节：</strong>${esc(characterWardrobe)}</p><p><strong>口播气质：</strong>${esc(character.voiceStyle || '亲切、专业、自然中文带看')}</p></div><div><p class="hint">Seedance 生成时必须同时在 prompt 和请求体里使用 sssid / asset:// 人像资产；不得随机换人。</p></div></div></section>` : '';
const countChars = (text) => String(text || '').replace(/[\s，。！？、,.!?：:；;“”"'（）()《》<>【】\[\]-]/g, '').length;
const refDuration = globalRefs.reduce((sum, item) => sum + Number(item.durationSeconds || item.duration || 0), 0);
const imageCards = (ids = []) => ids.map((id) => {
  const image = resolveImage(id);
  const src = image.url || image.cdnUrl || image.localPreviewUrl || '';
  return `<figure><img src="${esc(src)}" alt="${esc(image.title || image.id)}" loading="lazy"/><figcaption>${esc(image.title || image.id)}</figcaption></figure>`;
}).join('');
const candidateCards = candidates.length ? `<section class="panel"><h2>虚拟模特候选</h2><div class="cards people">${candidates.map((item, index) => `<article class="person ${item.assetUri === plan.aiCharacter?.assetUri || item.assetId === plan.aiCharacter?.assetId ? 'selected' : ''}"><div class="badge">${index === 0 ? '推荐' : '候选 ' + (index + 1)}</div><h3>${esc(item.displayLabel || item.assetId)}</h3><p><strong>${esc(item.assetUri || ('asset://' + (item.assetId || '')))}</strong></p><p>${esc(item.gender || '')} ${esc(item.age || '')} ${esc(item.userLabel || '')}</p><p>${esc(item.selectionRationale || item.matchReason || item.userLabelNotes || '')}</p></article>`).join('')}</div></section>` : '';
const referenceCards = globalRefs.length ? `<section class="panel"><h2>全局参考视频</h2><p class="hint">所有参考视频合计 ${esc(refDuration || '未填写')} 秒；Seedance 参考视频总时长必须不超过 15 秒。每个参考方面只能选择一个主视频。</p><div class="cards refs">${globalRefs.map((item) => `<article class="ref"><video src="${esc(item.url || item.video_url)}" controls preload="metadata"></video><h3>${esc(item.title || item.key)}</h3><p><strong>参考方面：</strong>${esc(Array.isArray(item.referenceUse) ? item.referenceUse.join(' / ') : item.referenceUse || '')}</p><p>${esc(item.referenceNotes || item.summary || '')}</p></article>`).join('')}</div></section>` : '';
const storyboardSrc = storyboard ? (storyboard.imageUrl || storyboard.cdnUrl || storyboard.url || '') : '';
const storyboardCdnWarning = storyboard && !/^https?:\/\//i.test(String(storyboardSrc || '')) ? '<p class="warning">分镜草图未使用 CDN URL，正式交付前必须先上传到 IDK/OSS。</p>' : '';
const storyboardCards = (storyboard || storyboardPanels.length) ? `<section class="panel storyboard"><h2>分镜草图</h2><p class="hint">分镜草图必须由 Codex 原生绘图生成，只控制镜头站位、运镜节奏和构图，不作为最终空间效果图。</p>${storyboardCdnWarning}${storyboardSrc ? `<figure class="storyboard-sheet"><img src="${esc(storyboardSrc)}" alt="分镜草图" loading="eager"/><figcaption>${esc(storyboard?.purpose || '中文粗线稿分镜图')}</figcaption></figure>` : ''}${storyboard?.prompt ? `<p><strong>草图提示词：</strong>${esc(storyboard.prompt)}</p>` : ''}${storyboardPanels.length ? `<table><thead><tr><th>时间</th><th>镜头</th><th>草图内容</th><th>镜头提示</th><th>转场</th></tr></thead><tbody>${storyboardPanels.map((panel) => `<tr><td>${esc(panel.timeRange || `${panel.start ?? ''}-${panel.end ?? ''}s`)}</td><td>${esc(panel.shotId || panel.panelId || '')}</td><td>${esc(panel.roughVisual || panel.visual || '')}</td><td>${esc(panel.cameraCue || panel.camera || '')}</td><td>${esc(panel.transitionCue || panel.transition || '')}</td></tr>`).join('')}</tbody></table>` : ''}</section>` : '';
const dialogueBlock = (shot) => {
  const lines = shot.dialogueLines || (shot.voiceover?.text ? [shot.voiceover] : []);
  if (!lines.length) return '';
  return `<div class="dialogue"><h3>台词与语速</h3>${lines.map((line) => {
    const chars = line.charCountNoPunctuation ?? countChars(line.text);
    const start = Number(line.start ?? line.speechStartSec ?? shot.startSec ?? 0);
    const end = Number(line.end ?? line.speechEndSec ?? (start + Number(shot.durationSec || 0)));
    const cps = line.charsPerSecond ?? (end > start ? chars / (end - start) : 0);
    return `<p><strong>${esc(line.speakerName || shot.voiceover?.speakerName || '旁白')}</strong> ${esc(start.toFixed(1))}-${esc(end.toFixed(1))}s · ${esc(chars)}字 · ${esc(Number(cps).toFixed(2))}字/s<br/>${esc(line.text || '')}</p>`;
  }).join('')}</div>`;
};
const beatTable = (shot) => {
  const beats = shot.microBeats || shot.timeline || [];
  if (!beats.length) return '';
  return `<table class="beat-table"><thead><tr><th>时间</th><th>机位/景别</th><th>镜头路径</th><th>构图/运动</th><th>转场</th><th>焦点细节</th><th>台词</th><th>BGM/SFX/灯光</th></tr></thead><tbody>${beats.map((beat) => {
    const camera = [beat.shotSize, beat.camera].filter(Boolean).join(' / ');
    const motion = [beat.framing, beat.movement, beat.visualAction || beat.screenAction].filter(Boolean).join('；');
    const transitions = [beat.transitionIn ? `入：${beat.transitionIn}` : '', beat.transitionOut ? `出：${beat.transitionOut}` : ''].filter(Boolean).join('；');
    const detail = [beat.focusObject, beat.detailCue].filter(Boolean).join('；');
    const sound = [beat.bgmCue ? `BGM：${beat.bgmCue}` : '', beat.sfxCue ? `SFX：${beat.sfxCue}` : '', beat.lightingCue ? `灯光：${beat.lightingCue}` : ''].filter(Boolean).join('；');
    return `<tr><td>${esc(beat.start ?? '')}-${esc(beat.end ?? '')}s</td><td>${esc(camera)}</td><td>${esc(beat.cameraPath || '')}</td><td>${esc(motion)}</td><td>${esc(transitions)}</td><td>${esc(detail)}</td><td>${esc(beat.dialogue || '')}</td><td>${esc(sound)}</td></tr>`;
  }).join('')}</tbody></table>`;
};
const html = `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>${esc(plan.title || '视频方案预览')}</title>
<style>
.warning{color:#9b2c2c;background:#fff5f5;border:1px solid #feb2b2;padding:10px 12px}
:root{color-scheme:light;--bg:#f6f1e9;--ink:#2a211b;--muted:#77685d;--line:#ded2c3;--accent:#a97648;--paper:#fffaf2;--good:#276749}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:"Noto Sans SC","PingFang SC","Microsoft YaHei",Arial,sans-serif}main{max-width:1180px;margin:0 auto;padding:40px 22px 72px}.hero{display:grid;grid-template-columns:1.2fr .8fr;gap:28px;align-items:end;border-bottom:1px solid var(--line);padding-bottom:28px}h1{font-size:42px;line-height:1.12;margin:0 0 14px;letter-spacing:0}.summary{font-size:17px;line-height:1.8;color:var(--muted);margin:0}.meta,.panel,.shot{background:var(--paper);border:1px solid var(--line)}.meta{padding:18px 20px}.meta div{display:flex;justify-content:space-between;gap:18px;border-bottom:1px solid #eadfd2;padding:8px 0}.meta div:last-child{border-bottom:0}.panel{margin-top:26px;padding:22px}.panel h2{margin:0 0 14px;font-size:24px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}.person,.ref{background:#fff;border:1px solid var(--line);padding:14px}.person.selected{border-color:var(--good);box-shadow:inset 0 0 0 2px rgba(39,103,73,.15)}.badge{display:inline-block;color:#fff;background:var(--accent);padding:3px 8px;font-size:12px;margin-bottom:8px}.ref video{display:block;width:100%;aspect-ratio:16/9;background:#000}.hint{color:var(--muted);line-height:1.7}.shot{display:grid;grid-template-columns:220px 1fr;gap:24px;margin-top:28px;padding:24px}.time{font-weight:700;color:var(--accent);font-size:20px}.shot h2{margin:2px 0 10px;font-size:24px}.shot p{margin:8px 0;color:var(--muted);line-height:1.7}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px;margin-top:16px}figure{margin:0;border:1px solid var(--line);background:#fff;min-width:0}img{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;background:#eee}figcaption{padding:8px 10px;font-size:13px;color:var(--muted)}.dialogue{border-top:1px solid var(--line);margin-top:16px;padding-top:12px}.dialogue h3{margin:0 0 8px;font-size:16px}table{width:100%;border-collapse:collapse;margin-top:14px;background:#fff}th,td{border:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top;font-size:13px;line-height:1.55}th{background:#f2e7d9}.storyboard-sheet img{aspect-ratio:auto;max-height:720px;object-fit:contain;background:#fbf7ef}.storyboard table td:nth-child(3){min-width:260px}.character-grid{display:grid;grid-template-columns:1.2fr .8fr;gap:18px}.character p{line-height:1.7}@media(max-width:760px){.character-grid{grid-template-columns:1fr}}@media(max-width:760px){.hero,.shot{grid-template-columns:1fr}h1{font-size:32px}}
</style>
</head>
<body><main>
<section class="hero"><div><h1>${esc(plan.title || '视频方案预览')}</h1><p class="summary">${esc(plan.summary || '')}</p></div><div class="meta"><div><span>总时长</span><strong>${esc(plan.totalDurationSec || '')}s</strong></div><div><span>比例</span><strong>${esc(plan.aspectRatio || '16:9')}</strong></div><div><span>人物</span><strong>${esc(plan.aiCharacter?.assetUri || (plan.aiCharacter?.enabled ? '需要人物' : '不需要人物'))}</strong></div><div><span>参考视频</span><strong>${esc(globalRefs.length)} 个 / ${esc(refDuration || 0)}s</strong></div></div></section>
${characterPanel}
${candidateCards}
${referenceCards}
${storyboardCards}
${shots.map((shot, index) => `<section class="shot"><div><div class="time">${esc(shot.startSec ?? '')}s - ${esc((Number(shot.startSec || 0)+Number(shot.durationSec || 0)).toFixed(1))}s</div><p>Shot ${index + 1}</p></div><div><h2>${esc(shot.title || `镜头 ${index + 1}`)}</h2><p><strong>运镜：</strong>${esc(shot.cameraMove || shot.cameraPath || '')}</p><p><strong>提示词：</strong>${esc(shot.prompt || '')}</p><p>${esc(shot.notes || '')}</p>${dialogueBlock(shot)}${beatTable(shot)}<div class="grid">${imageCards([...(shot.imageIds || shot.imageOrder || []), ...(shot.detailAssetIds || [])])}</div></div></section>`).join('\n')}
</main></body></html>`;
fs.mkdirSync(path.dirname(path.resolve(outPath)), { recursive: true });
fs.writeFileSync(outPath, html);
console.log(JSON.stringify({ ok: true, outPath, shots: shots.length, characterCandidates: candidates.length, globalReferences: globalRefs.length }, null, 2));
