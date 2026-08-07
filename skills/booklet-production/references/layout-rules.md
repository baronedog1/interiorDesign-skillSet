# Layout Rules And Reference Notes

## Reference Assets

The bundled screenshots are visual references only. Do not copy their protected imagery into deliverables.

- `assets/reference-images/yabu-approach-collage.jpg`: large white space, asymmetric image rhythm, poetic small text.
- `assets/reference-images/yabu-services-split.jpg`: pure background, large serif type, one dominant image block.
- `assets/reference-images/yabu-portfolio-grid.jpg`: portfolio grid with strong color; use saturated color sparingly.
- `assets/reference-images/avroko-detail-story.jpg`: large editorial title, short narrative copy, detail image pairing.

## Chinese-First Copy

Default copy hierarchy:

- Small label: English + Chinese, e.g. `Design Concept / 设计概念`
- Main heading: Chinese
- Body: Chinese
- Captions: Chinese unless they are file/source identifiers

Stable review-derived rules:

- Cover pages use Chinese as the primary title; English may appear only as a small bilingual label.
- Concept pages should speak about design value, not production process. If a page has major whitespace, give it a visual anchor.
- Gallery/detail pages should use real generated images or true detail images, and saturated red backgrounds only when the content needs that emphasis.

Avoid process copy:

- Bad: “本页采用留白和错落排版。”
- Better: “浅色基底让木作和灯光成为空间的主角。”

## Page Types

- Cover: project name or design theme, one strong image, brief design essence.
- Concept: 3-4 design principles with one supporting image if there is major whitespace.
- Full-bleed space page: one room image with small bilingual label, Chinese title, one short design sentence.
- Detail page: real generated/detail images showing material, light, texture, edge, hardware, or furniture.
- Sequence/gallery page: 3-4 related images showing public zone, private zone, bathing rooms, arrival sequence, etc.
- Closing page: contact, website, producer mark, optional QR code.

## Layout Mode Selection Contract

Before building HTML/CSS, assign each page a layout mode and reason.

Recommended modes:

- `full-bleed`: one strong room image fills the page; use for hero public space, dramatic bedroom, balcony view, or closing visual.
- `left-copy-right-image` / `left-image-right-copy`: alternate copy/image direction to break rhythm; use for quieter rooms and explanatory pages.
- `multi-image-gallery`: 2-4 related images on one page; use for public-zone sequence, bedroom + wardrobe, bath + service spaces, or before/after/source/render context.
- `detail-story`: one dominant image plus 2-3 details; use for materials, lighting, furniture, cabinetry, kitchen, bath, and balcony equipment.
- `material-board`: palette, texture, furniture, and render fragments together; use once for style synthesis.
- `floorplan-logic`: floor plan, relationship diagram, and concise text; use when explaining structure, circulation, or zoning.

Rhythm rules:

- Do not let all space pages become the same left-image/right-copy template.
- Do not repeat the same layout mode for more than 2 consecutive pages unless the user asks for a strict catalog format.
- Prefer at least 4 distinct layout modes in booklets longer than 10 pages.
- For 12-space interior booklets, include at least one full-bleed room page, one multi-image page, one detail/material page, and one reversed text/image page.
- Record the mode in `page-specs.json` so QA can verify visual rhythm, not only PDF validity.


## Palette Guidance

Preferred:

- Warm white / ivory / pale stone
- Soft gray / greige
- Pale sage / muted green-gray
- Charcoal / near black
- Low-saturation warm wood

Use sparingly:

- Saturated red, orange, purple, bright blue
- Heavy gradients
- Decorative blobs or strong brand color blocks without reason

## Watermark Patterns

Default CSS pattern:

```css
.page::after {
  content: "www.baiende.com · 百恩得出品";
  position: absolute;
  left: 20mm;
  right: 20mm;
  bottom: 6mm;
  text-align: center;
  font-size: 7.5px;
  color: rgba(30, 29, 26, .38);
  letter-spacing: .5px;
}
.full::after, .dark::after {
  color: rgba(255,255,255,.72);
  text-shadow: 0 1px 12px rgba(0,0,0,.45);
}
```

## Mobile-Safe PDF Export

When the booklet will be opened in Feishu, WeChat, iOS preview, Android preview, or other embedded mobile PDF viewers, create a mobile-safe copy in addition to the high quality PDF.

Recommended Ghostscript pattern:

```bash
gs -sDEVICE=pdfwrite -dCompatibilityLevel=1.4 \
  -dNOPAUSE -dQUIET -dBATCH \
  -dUseCIEColor=false -sColorConversionStrategy=RGB \
  -dProcessColorModel=/DeviceRGB -dConvertCMYKImagesToRGB=true \
  -dDetectDuplicateImages=true \
  -dDownsampleColorImages=true -dDownsampleGrayImages=true \
  -dColorImageResolution=220 -dGrayImageResolution=220 \
  -dColorImageDownsampleType=/Bicubic -dGrayImageDownsampleType=/Bicubic \
  -dEncodeColorImages=true -dEncodeGrayImages=true \
  -dAutoFilterColorImages=false -dColorImageFilter=/DCTEncode \
  -dAutoFilterGrayImages=false -dGrayImageFilter=/DCTEncode \
  -dJPEGQ=85 \
  -sOutputFile=booklet-mobile-safe.pdf booklet-high-quality.pdf
```

Verify with:

```bash
pdfimages -list booklet-mobile-safe.pdf
```

Expected image color spaces are `rgb` or `gray`. If the output repeatedly reports `read ICCBased color space profile error`, regenerate before delivery.

## Detail Image Decision Matrix

| Trigger | Required action | Notes |
| --- | --- | --- |
| Major room / hero room | Main render plus one detail or alternate angle unless skipped with reason | Living room, dining room, primary bedroom, open public zone |
| Confirmed replacement furniture | Furniture close-up or lifestyle detail | Explain scale, material, fit, proportion |
| Material or lighting highlight | Material close-up or lighting mood detail | Use native generation rather than low-res crop |
| Secondary space with functional highlight | One local detail image | Storage, hardware, balcony utility, bath fixture |
| No highlight and low priority | One main image is acceptable | Record `skipReason` in detailImagePlan |

## Detail Image Prompt Pattern

Use Codex native image generation for real detail imagery:

```text
高端住宅室内设计细节特写，主题：[材质/节点]，
包含：[木纹/石材/织物/灯带/五金/柜内收纳]，
风格：现代简约、安静高级、真实摄影质感、浅景深、柔和暖光，
A4图册可用横向构图。
不要文字，不要logo，不要水印，不要人物。
```
