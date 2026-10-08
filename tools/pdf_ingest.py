#!/usr/bin/env python3
"""Extract text and render selected pages from a company-report PDF.

Examples:
  python pdf_ingest.py annual_report.pdf --outdir work/report --pages 1-12,27-40
  python pdf_ingest.py annual_report.pdf --outdir work/report --pages 5-12 --ocr
  python pdf_ingest.py report.pdf --outdir work/report --pages all

OCR is optional. --ocr prefers Tesseract with chi_sim, then RapidOCR; if neither
is available, the tool still renders selected pages for visual inspection.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pymupdf


def parse_pages(spec: str | None, page_count: int) -> list[int]:
    if not spec:
        return list(range(min(10, page_count)))
    if spec.strip().lower() == "all":
        return list(range(page_count))
    selected: set[int] = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            left, right = chunk.split("-", 1)
            start, end = int(left), int(right)
        else:
            start = end = int(chunk)
        if start < 1 or end < start or end > page_count:
            raise ValueError(f"页码范围无效：{chunk}（PDF 共 {page_count} 页）")
        selected.update(range(start - 1, end))
    return sorted(selected)


def cjk_count(text: str) -> int:
    return sum("\u4e00" <= char <= "\u9fff" for char in text)


def extract_native(pdf: Path, doc: pymupdf.Document, outdir: Path) -> str:
    pdftotext = shutil.which("pdftotext")
    text_path = outdir / "native_text.txt"
    if pdftotext:
        result = subprocess.run(
            [pdftotext, "-layout", str(pdf), str(text_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and text_path.exists():
            return text_path.read_text(encoding="utf-8", errors="replace")
    # Fallback retains per-page separators, though layout may be weaker.
    text = "\n\n".join(f"--- PAGE {i + 1} ---\n{page.get_text('text', sort=True)}" for i, page in enumerate(doc))
    text_path.write_text(text, encoding="utf-8")
    return text


def tesseract_info() -> tuple[str | None, set[str]]:
    binary = shutil.which("tesseract")
    if not binary:
        return None, set()
    result = subprocess.run([binary, "--list-langs"], capture_output=True, text=True, check=False)
    langs = set()
    for line in (result.stdout + result.stderr).splitlines():
        line = line.strip()
        if line and not line.lower().startswith("list of available"):
            langs.add(line)
    return binary, langs


def main() -> int:
    parser = argparse.ArgumentParser(description="公司财报 PDF 文本抽取、中文可读性检查及页面渲染")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--pages", help="要渲染/OCR 的 1-based 页码，如 5-12,27-40；默认前 10 页；all 表示全部")
    parser.add_argument("--dpi", type=int, default=180)
    parser.add_argument("--ocr", action="store_true", help="使用 Tesseract chi_sim 或 RapidOCR 对选定页 OCR")
    args = parser.parse_args()
    if not args.pdf.is_file():
        parser.error(f"找不到 PDF：{args.pdf}")
    args.outdir.mkdir(parents=True, exist_ok=True)

    try:
        doc = pymupdf.open(args.pdf)
    except Exception as exc:
        parser.error(f"无法打开 PDF：{exc}")
    pages = parse_pages(args.pages, len(doc))
    text = extract_native(args.pdf, doc, args.outdir)
    chosen_text = "\n".join(doc[i].get_text("text", sort=True) for i in pages)
    cjk = cjk_count(chosen_text)
    cjk_per_page = cjk / max(1, len(pages))

    rendered_dir = args.outdir / "pages"
    rendered_dir.mkdir(exist_ok=True)
    image_paths: list[Path] = []
    scale = args.dpi / 72
    for index in pages:
        image = rendered_dir / f"page_{index + 1:04d}.png"
        doc[index].get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).save(image)
        image_paths.append(image)

    notes = [
        f"PDF：{args.pdf.resolve()}",
        f"页数：{len(doc)}；渲染页数：{len(pages)}；原生抽取中文字符数（所选页）：{cjk}（平均 {cjk_per_page:.1f}/页）",
        f"原生全文：{(args.outdir / 'native_text.txt').resolve()}",
        f"页面图片目录：{rendered_dir.resolve()}",
    ]
    if cjk_per_page < 10:
        notes.append("警告：所选页的原生文本层中文字符很少，可能是字体映射问题；请优先查看页面图片/OCR，不要仅据 native_text.txt 引用表格标签。")
    if args.ocr:
        binary, langs = tesseract_info()
        ocr_blocks = []
        if binary and "chi_sim" in langs:
            for index, image in zip(pages, image_paths):
                result = subprocess.run(
                    [binary, str(image), "stdout", "-l", "chi_sim+eng", "--psm", "6"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode != 0:
                    notes.append(f"Tesseract OCR 第 {index + 1} 页失败：{result.stderr.strip()}")
                    continue
                ocr_blocks.append(f"--- PAGE {index + 1} ---\n{result.stdout}")
            ocr_engine = "Tesseract chi_sim+eng"
        else:
            try:
                from rapidocr_onnxruntime import RapidOCR
                engine = RapidOCR()
                for index, image in zip(pages, image_paths):
                    result, _elapsed = engine(str(image))
                    snippets = []
                    for item in result or []:
                        box, text, score = item
                        x = min(point[0] for point in box)
                        y = min(point[1] for point in box)
                        snippets.append((round(y), round(x), float(score), str(text)))
                    snippets.sort(key=lambda item: (item[0], item[1]))
                    body = "\n".join(f"y={y:05d} x={x:05d} [{score:.2f}] {text}" for y, x, score, text in snippets)
                    ocr_blocks.append(f"--- PAGE {index + 1} ---\n{body}")
                ocr_engine = "RapidOCR（中文识别；字符/顺序可能有误）"
            except ImportError:
                notes.append("OCR 未执行：未安装中文 OCR。页面图片已生成，可安装 tools/requirements-ocr.txt 后重试，或直接视觉核对。")
                ocr_engine = "unavailable"
            except Exception as exc:
                notes.append(f"RapidOCR 执行失败：{exc}")
                ocr_engine = "failed"
        if ocr_blocks:
            ocr_path = args.outdir / "ocr_selected_pages.txt"
            ocr_path.write_text("\n\n".join(ocr_blocks), encoding="utf-8")
            notes.append(f"OCR 引擎：{ocr_engine}")
            notes.append(f"OCR 文本：{ocr_path.resolve()}（识别结果仍需与 PDF 原页抽查）")

    (args.outdir / "README.txt").write_text("\n".join(notes) + "\n", encoding="utf-8")
    print("\n".join(notes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
