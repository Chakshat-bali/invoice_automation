"""
OCR and Computer Vision Layer
------------------------------
Primary engine: PaddleOCR with PP-StructureV3 (layout + table recognition).
Fallback engine: RapidOCR (ONNX, no PaddlePaddle dependency) for when
PaddleOCR isn't available/installed or for a fast text-only pass.

Both engines are lazy-loaded (only imported/instantiated on first use) so the
rest of the app can run/be tested without the heavy OCR deps installed.
"""
from functools import lru_cache
from typing import Dict, List

from app.config import settings


@lru_cache(maxsize=1)
def _get_paddle_engine():
    from paddleocr import PPStructureV3
    # PP-StructureV3 gives layout blocks + table structure + OCR text in one pass.
    return PPStructureV3(use_doc_orientation_classify=True,
                          use_doc_unwarping=False,
                          use_textline_orientation=True)


@lru_cache(maxsize=1)
def _get_rapid_engine():
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR()


def run_paddle_structure(image_path: str) -> Dict:
    """
    Returns:
      {
        "full_text": str,
        "avg_confidence": float,
        "blocks": [{"text": str, "confidence": float, "bbox": [...], "type": "text|table"}],
        "tables": [{"bbox": [...], "html": str, "cells": [[...]]}]
      }
    """
    engine = _get_paddle_engine()
    output = engine.predict(image_path)

    blocks, tables, texts, confidences = [], [], [], []

    for res in output:
        # PPStructureV3 result objects expose a `.json`/dict-like structure with
        # `parsing_res_list` containing layout blocks (text, table, title, etc).
        data = res.json if hasattr(res, "json") else res
        parsing = data.get("parsing_res_list", []) if isinstance(data, dict) else []
        for block in parsing:
            block_type = block.get("block_label", "text")
            content = block.get("block_content", "")
            bbox = block.get("block_bbox", [])
            if block_type == "table":
                tables.append({"bbox": bbox, "html": content})
            else:
                blocks.append({"text": content, "confidence": block.get("score", 0.85),
                                "bbox": bbox, "type": block_type})
                if content:
                    texts.append(content)
                    confidences.append(block.get("score", 0.85))

    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return {
        "engine": "paddleocr_pp_structure_v3",
        "full_text": "\n".join(texts),
        "avg_confidence": round(avg_conf, 3),
        "blocks": blocks,
        "tables": tables,
    }


def run_rapidocr(image_path: str) -> Dict:
    engine = _get_rapid_engine()
    result, _ = engine(image_path)
    if not result:
        return {"engine": "rapidocr", "full_text": "", "avg_confidence": 0.0, "blocks": [], "tables": []}

    blocks, texts, confidences = [], [], []
    for bbox, text, conf in result:
        blocks.append({"text": text, "confidence": float(conf), "bbox": bbox, "type": "text"})
        texts.append(text)
        confidences.append(float(conf))

    return {
        "engine": "rapidocr",
        "full_text": "\n".join(texts),
        "avg_confidence": round(sum(confidences) / len(confidences), 3) if confidences else 0.0,
        "blocks": blocks,
        "tables": [],
    }


def extract_text_and_layout(image_path: str, prefer: str | None = None) -> Dict:
    """
    Runs the primary engine, falling back automatically on failure/import error.
    `prefer` defaults to settings.ocr_prefer.
    """
    if prefer is None:
        prefer = settings.ocr_prefer

    engines = [run_paddle_structure, run_rapidocr] if prefer == "paddle" \
        else [run_rapidocr, run_paddle_structure]

    last_err = None
    for engine_fn in engines:
        try:
            result = engine_fn(image_path)
            if result["full_text"].strip():
                return result
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue

    return {
        "engine": "none",
        "full_text": "",
        "avg_confidence": 0.0,
        "blocks": [],
        "tables": [],
        "error": str(last_err) if last_err else "no text extracted",
    }


def merge_pages(page_results: List[Dict]) -> Dict:
    """Merge multi-page OCR results into a single document-level result."""
    full_text = "\n\n--- page break ---\n\n".join(r["full_text"] for r in page_results)
    all_confidences = [r["avg_confidence"] for r in page_results if r["avg_confidence"] > 0]
    tables = [t for r in page_results for t in r.get("tables", [])]
    blocks = [b for r in page_results for b in r.get("blocks", [])]
    return {
        "full_text": full_text,
        "avg_confidence": round(sum(all_confidences) / len(all_confidences), 3) if all_confidences else 0.0,
        "blocks": blocks,
        "tables": tables,
        "page_count": len(page_results),
    }
