# Storyboard Sketch and Copywriting Method

Purpose: use this reference when an interior design video plan needs a virtual model / design guide, storyboard sketch, dialogue, detailed camera movement and BGM/SFX.

## 1. Storyboard Sketch

- First split the video into 1-2 second panels. A 30 second guided tour usually needs 12-18 rough panels.
- Generate one rough storyboard sheet with Codex native image generation in the current Codex session.
- The sheet must look like loose pencil / marker line art, not a polished render.
- Each panel must show: time range, shot number, camera direction arrows, presenter position, focus object, transition hint.
- The sheet only controls camera blocking, movement, composition and rhythm. It does not replace the current design render and must not be used as proof of final spatial effect.
- Do not use PIL, SVG, HTML, canvas, script output, screenshots with drawn boxes, or any code-generated placeholder as the storyboard image.

Prompt pattern:

```text
Create a rough pencil storyboard sheet for a 30-second Chinese luxury interior design guided tour.
Style: loose hand-drawn black and warm-gray line art, low-detail, quick director sketch, no polished rendering.
Layout: 15 panels in a 5x3 grid, each panel has timecode, shot number, camera arrows, presenter position and focus label.
Content: virtual female design guide leads viewers through the current living-dining room; panels show dining table and pendant light, open living-dining connection, TV wall material, sofa wall soft light, detail push-ins.
Camera language: soft fade in, left-to-right slide, slow push-in, close-up, gentle orbit, match cut by light and material.
Do not invent a new room. Use abstract sketch symbols only; do not copy external reference space.
```

## 2. Dialogue

The voiceover is the core of the plan. It must sound like a friendly design consultant guiding a client, not a stiff report.

Good opening examples:

- 来，我们一起看看这套五口之家的中式轻奢客餐厅。
- 一进来，你会先感受到这个空间很稳：圆桌、吊灯和客厅的开阔动线，把一家人的日常聚在一起。
- 你看这里不是简单地摆一套餐桌，而是用灯光和木质把吃饭、聊天、陪孩子的场景串起来。

Forbidden weak openings:

- 本案采用中式轻奢风格。
- 这个空间高级舒适。
- 这里满足了客户需求。

Every sentence should point to a visible detail: circulation, lighting, family interaction, round table, pendant light, wood veneer, stone texture, sofa scale, TV wall storage, material transition or close-up object.

## 3. Camera and Sound

Every shot must contain precise micro-beats:

- time range, usually 1-2 seconds per panel;
- shot size: wide / medium / close-up / detail;
- camera path: left-to-right slide, slow push-in, pull-back, slight orbit, tilt, match cut;
- transition in/out: soft fade, dissolve, match cut by light, cut on movement;
- focus object and detail cue;
- BGM cue: warm piano, guqin, light strings, quiet modern lounge;
- SFX cue: soft footsteps, subtle fabric movement, gentle room tone, pendant-light chime, tableware touch.

The rule is: dialogue decides duration; camera changes every 3-4 seconds; if one Seedance clip is 5 seconds, it still needs at least two internal micro-beats.

## 分镜草图中文提示词模板

用于 Codex 原生绘图生成粗线稿分镜图时，必须把下面要求写进提示词：

```text
请画一张潦草铅笔/马克笔线稿风格的室内设计视频分镜图，不要精修，不要彩色效果图。
全部文字必须使用简体中文，禁止英文标签。
每个小格标出中文时间码、镜头号、模特站位、镜头运动箭头、焦点物件和转场提示。
只表达镜头站位、人物位置、推拉摇移、局部特写和空间关系；不要画成正式效果图。
```

生成后必须把分镜图上传到 IDK/OSS，`video-storyboard-plan.json` 只能写 CDN URL；HTML 和 Seedance 请求不得引用本地路径。
