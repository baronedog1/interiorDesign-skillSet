#!/usr/bin/env python3
"""Run deterministic PDF QA checks for booklet deliverables."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=False)


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"Required tool not found: {name}")
    return path


def parse_pdfinfo(output: str) -> dict[str, object]:
    pages = None
    encrypted = None
    page_size = None
    for line in output.splitlines():
        if line.startswith("Pages:"):
            match = re.search(r"(\d+)", line)
            pages = int(match.group(1)) if match else None
        elif line.startswith("Encrypted:"):
            encrypted = line.split(":", 1)[1].strip()
        elif line.startswith("Page size:"):
            page_size = line.split(":", 1)[1].strip()
    return {"pages": pages, "encrypted": encrypted, "pageSize": page_size}


def parse_pdfimages(stdout: str, stderr: str) -> dict[str, object]:
    color_spaces: dict[str, int] = {}
    image_count = 0
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) < 6 or not parts[0].isdigit():
            continue
        image_count += 1
        color = parts[5].lower()
        color_spaces[color] = color_spaces.get(color, 0) + 1

    combined = f"{stdout}\n{stderr}".lower()
    risky_terms = ["read iccbased color space profile error", "iccbased", "icc"]
    risky_colors = [name for name in color_spaces if name not in {"rgb", "gray", "index"}]
    return {
        "imageCount": image_count,
        "colorSpaces": color_spaces,
        "riskyColors": risky_colors,
        "iccRiskDetected": any(term in combined for term in risky_terms) or bool(risky_colors),
        "stderr": stderr.strip(),
    }


def parse_preview_pages(value: str, page_count: int | None) -> list[int]:
    pages: list[int] = []
    for token in [part.strip().lower() for part in value.split(",") if part.strip()]:
        if token == "first":
            page = 1
        elif token == "last":
            if not page_count:
                continue
            page = page_count
        else:
            try:
                page = int(token)
            except ValueError:
                continue
            if page < 0 and page_count:
                page = page_count + page + 1
        if page >= 1 and (not page_count or page <= page_count) and page not in pages:
            pages.append(page)
    return pages


def render_previews(pdf_path: Path, out_dir: Path, pages: list[int]) -> list[str]:
    if not pages:
        return []
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        return []
    preview_dir = out_dir / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    rendered: list[str] = []
    for page in pages:
        prefix = preview_dir / f"page-{page:03d}"
        result = run_command(
            [
                pdftoppm,
                "-png",
                "-f",
                str(page),
                "-l",
                str(page),
                "-singlefile",
                str(pdf_path),
                str(prefix),
            ]
        )
        output = prefix.with_suffix(".png")
        if result.returncode == 0 and output.exists():
            rendered.append(str(output))
    return rendered


def write_markdown(report: dict[str, object], path: Path) -> None:
    warnings = report.get("warnings", [])
    preview_files = report.get("previewFiles", [])
    pdfinfo = report.get("pdfinfo", {})
    pdfimages = report.get("pdfimages", {})
    lines = [
        "# PDF QA Report",
        "",
        f"- File: `{report['pdf']}`",
        f"- Size: {report['sizeMb']} MB",
        f"- Pages: {pdfinfo.get('pages')}",
        f"- Page size: {pdfinfo.get('pageSize')}",
        f"- Encrypted: {pdfinfo.get('encrypted')}",
        f"- Sendable limit: {report['maxSendableMb']} MB",
        f"- Sendable: {report['sendable']}",
        f"- Image count: {pdfimages.get('imageCount')}",
        f"- Color spaces: `{json.dumps(pdfimages.get('colorSpaces', {}), sort_keys=True)}`",
        f"- ICC risk detected: {pdfimages.get('iccRiskDetected')}",
        "",
        "## Warnings",
        "",
    ]
    if warnings:
        lines.extend([f"- {item}" for item in warnings])
    else:
        lines.append("- None")
    lines.extend(["", "## Preview Files", ""])
    if preview_files:
        lines.extend([f"- `{item}`" for item in preview_files])
    else:
        lines.append("- None")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check PDF metadata, image color spaces, previews, and sendable size.")
    parser.add_argument("pdf", help="PDF file to inspect.")
    parser.add_argument("--out-dir", default=None, help="Directory for QA reports and previews. Defaults to <pdf-dir>/qa.")
    parser.add_argument("--preview-pages", default="first,last", help="Comma list: first,last,1,2,-1. Default: first,last.")
    parser.add_argument("--max-sendable-mb", type=float, default=30.0, help="Feishu/mobile sendable size limit.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when warnings are found.")
    args = parser.parse_args()

    pdf_path = Path(args.pdf).expanduser().resolve()
    if not pdf_path.exists():
        raise SystemExit(f"PDF not found: {pdf_path}")
    if not pdf_path.is_file():
        raise SystemExit(f"Not a file: {pdf_path}")

    out_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else pdf_path.parent / "qa"
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        pdfinfo = require_tool("pdfinfo")
        pdfimages = require_tool("pdfimages")
    except RuntimeError as exc:
        raise SystemExit(str(exc))

    info_result = run_command([pdfinfo, str(pdf_path)])
    images_result = run_command([pdfimages, "-list", str(pdf_path)])

    if info_result.returncode != 0:
        raise SystemExit(info_result.stderr.strip() or "pdfinfo failed")
    if images_result.returncode != 0:
        raise SystemExit(images_result.stderr.strip() or "pdfimages failed")

    info = parse_pdfinfo(info_result.stdout)
    images = parse_pdfimages(images_result.stdout, images_result.stderr)
    size_mb = round(pdf_path.stat().st_size / 1024 / 1024, 2)
    page_count = info.get("pages") if isinstance(info.get("pages"), int) else None
    pages = parse_preview_pages(args.preview_pages, page_count)
    previews = render_previews(pdf_path, out_dir, pages)

    warnings: list[str] = []
    if info.get("encrypted") not in {None, "no"}:
        warnings.append("PDF is encrypted; Feishu/mobile preview may fail.")
    if not info.get("pages"):
        warnings.append("Could not determine page count.")
    if size_mb > args.max_sendable_mb:
        warnings.append(f"File is larger than sendable limit: {size_mb} MB > {args.max_sendable_mb} MB.")
    if images.get("iccRiskDetected"):
        warnings.append("Potential ICCBased/non-RGB color risk detected. Re-export a DeviceRGB/sRGB compatible PDF.")
    if pages and not previews:
        warnings.append("No preview PNG files were rendered; check pdftoppm availability or PDF validity.")

    report = {
        "pdf": str(pdf_path),
        "sizeMb": size_mb,
        "maxSendableMb": args.max_sendable_mb,
        "sendable": size_mb <= args.max_sendable_mb,
        "pdfinfo": info,
        "pdfimages": images,
        "previewFiles": previews,
        "warnings": warnings,
        "ok": not warnings,
    }
    json_path = out_dir / "pdf-qa-report.json"
    md_path = out_dir / "pdf-qa-report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, md_path)
    print(json.dumps({"ok": report["ok"], "report": str(md_path), "json": str(json_path)}, ensure_ascii=False))
    return 1 if args.strict and warnings else 0


if __name__ == "__main__":
    sys.exit(main())
