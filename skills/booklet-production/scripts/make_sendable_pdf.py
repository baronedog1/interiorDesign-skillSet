#!/usr/bin/env python3
"""Create a mobile-safe/sendable RGB PDF with Ghostscript, then run QA."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert a booklet PDF to an RGB/mobile-safe sendable PDF.")
    parser.add_argument("input_pdf", help="High-resolution source PDF.")
    parser.add_argument("output_pdf", help="Output sendable/mobile-safe PDF.")
    parser.add_argument("--image-resolution", type=int, default=144, help="Downsample color/gray images to this PPI.")
    parser.add_argument("--max-sendable-mb", type=float, default=30.0, help="Expected sendable size limit.")
    parser.add_argument("--skip-qa", action="store_true", help="Do not run pdf_quality_check.py after conversion.")
    parser.add_argument("--strict-size", action="store_true", help="Exit non-zero if output remains above max size.")
    args = parser.parse_args()

    source = Path(args.input_pdf).expanduser().resolve()
    target = Path(args.output_pdf).expanduser().resolve()
    if not source.exists():
        raise SystemExit(f"Input PDF not found: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)

    gs = shutil.which("gs")
    if not gs:
        raise SystemExit("Ghostscript not found: install `gs` or export the PDF as RGB from the source project.")

    command = [
        gs,
        "-dSAFER",
        "-dBATCH",
        "-dNOPAUSE",
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.6",
        "-dDetectDuplicateImages=true",
        "-dEmbedAllFonts=true",
        "-dSubsetFonts=true",
        "-dAutoRotatePages=/None",
        "-sColorConversionStrategy=RGB",
        "-dProcessColorModel=/DeviceRGB",
        "-dDownsampleColorImages=true",
        f"-dColorImageResolution={args.image_resolution}",
        "-dDownsampleGrayImages=true",
        f"-dGrayImageResolution={args.image_resolution}",
        "-dDownsampleMonoImages=true",
        "-dMonoImageResolution=300",
        f"-sOutputFile={target}",
        str(source),
    ]
    result = run_command(command)
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or result.stdout.strip() or "Ghostscript conversion failed")
    if not target.exists():
        raise SystemExit(f"Ghostscript finished but output file was not created: {target}")

    size_mb = round(target.stat().st_size / 1024 / 1024, 2)
    qa_result: dict[str, object] | None = None
    if not args.skip_qa:
        checker = Path(__file__).resolve().parent / "pdf_quality_check.py"
        qa = run_command(
            [
                sys.executable,
                str(checker),
                str(target),
                "--out-dir",
                str(target.parent / "qa-sendable"),
                "--max-sendable-mb",
                str(args.max_sendable_mb),
            ]
        )
        try:
            qa_result = json.loads(qa.stdout.strip().splitlines()[-1]) if qa.stdout.strip() else None
        except json.JSONDecodeError:
            qa_result = {"ok": False, "stdout": qa.stdout, "stderr": qa.stderr}
        if qa.returncode != 0:
            raise SystemExit(qa.stderr.strip() or qa.stdout.strip() or "QA failed")

    response = {
        "ok": size_mb <= args.max_sendable_mb,
        "outputPdf": str(target),
        "sizeMb": size_mb,
        "maxSendableMb": args.max_sendable_mb,
        "qa": qa_result,
    }
    print(json.dumps(response, ensure_ascii=False))
    if args.strict_size and size_mb > args.max_sendable_mb:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
