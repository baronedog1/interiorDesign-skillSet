# AI Video Reference Library

This reference library is company-level AI Native/Data Knowledge infrastructure. It is not an IDK backend API and must not be named after Seedance.

## Source Of Record

- Database schema: `data_knowledge`
- Table: `ai_video_references`
- Access pattern: local AI Native skills query the table through a read-only database connection.
- Consumer: video storyboard planning, Seedance 2.0 generation, future video models, short drama and other AI video workflows.

## Selection Steps

1. Read the storyboard need: whole-home walkthrough, detail close-up, material story, furniture reveal, community teaser, or customer proposal.
2. Query with Chinese categorized tags and optional search text. For interior design videos, first hard-filter for design-related tags: `室内设计`; if insufficient, expand only to `家具设计`、`家居`、`空间设计`、`设计方案`、`样板间`、`软装`.
3. Prefer references whose title, summary, duration, aspect ratio and reference notes match the current storyboard. Do not use unrelated videos only because their camera looks good.
4. Select only global references. The sum of selected reference-video durations must be <=15 seconds. One reference aspect, such as 运镜、镜头质感、音频节奏、视频风格, can only have one owning video.
5. Write selected `reference_key`, `video_url`, `durationSeconds`, `referenceUse[]`, `referenceNotes` and storyboard hints into `globalReferenceVideos[]` in `video-storyboard-plan.json`. Do not write `shots[].referenceVideos[]` in new plans.
6. If no reference matches, write a clear no-reference reason and continue with image-based storyboard planning.

## Required Output Fields

- `aiVideoReferenceKeys[]`
- `globalReferenceVideos[]` with playable URLs, duration seconds, `referenceUse[]`, and reference notes
- `referenceNotes`
- `referenceStoryboardHints`

`referenceVideoUrls[]` is a deprecated read-only input field for old plans. New plans must use `globalReferenceVideos[]`.

IDK only receives final chosen assets, uploaded videos and community posts. It does not own this reference library.

## 2026-06-09 IDK interior design reference seed records

The company-level table `data_knowledge.ai_video_references` now contains three active IDK interior design references copied from existing IDK template videos:

- `idk-interior-design-slow-camera-v1`: slow multi-shot / whole-home walkthrough reference.
- `idk-interior-design-fixed-camera-reveal-v1`: fixed-camera furniture reveal and soft-staging reference.
- `idk-interior-design-fast-camera-v1`: faster dynamic camera / community teaser reference.

The original IDK OSS objects are retained for website compatibility. Skill workflows must use the copied objects under:

`ai/yeyiai/data-knowledge/ai-video-references/idk-interior-design/20260609/`
