"""
Pre-processing Layer
---------------------
Converts PDFs to images and cleans up scanned/photographed invoices so the
OCR layer has the best possible input: deskewed, denoised, contrast-enhanced,
correctly oriented. Also scores blur/resolution so bad scans can be flagged
early instead of silently producing garbage extractions.
"""
import os
from typing import List, Tuple

import cv2
import fitz  # PyMuPDF
import numpy as np
from PIL import Image

from app.config import settings

BLUR_THRESHOLD = 100.0        # Laplacian variance below this => likely blurry
MIN_DIMENSION = 800           # px; upscale if smaller


def is_native_pdf(file_path: str) -> bool:
    """Check if the PDF has a significant amount of extractable text, indicating it is native/digital."""
    if not file_path.lower().endswith(".pdf"):
        return False
    try:
        doc = fitz.open(file_path)
        total_text = ""
        for i, page in enumerate(doc):
            if i >= 3:
                break
            total_text += page.get_text()
        doc.close()
        return len(total_text.strip()) > 50
    except Exception:
        return False


def extract_native_pdf_text(pdf_path: str) -> Tuple[str, int]:
    """
    Extracts native digital text page-by-page.
    Blocks are sorted spatially (top-to-bottom, left-to-right) to preserve table structures.
    Returns:
        (combined_text, page_count)
    """
    try:
        doc = fitz.open(pdf_path)
        pages_text = []
        page_count = 0
        for i, page in enumerate(doc):
            if i >= 3:
                break
            page_count += 1
            blocks = page.get_text("blocks")
            # Sort blocks: top-to-bottom, then left-to-right
            blocks.sort(key=lambda b: (b[1], b[0]))
            page_text = "\n".join(b[4] for b in blocks if b[4].strip())
            pages_text.append(page_text)
        doc.close()
        return "\n\n--- page break ---\n\n".join(pages_text), page_count
    except Exception as e:
        return "", 0


def pdf_to_images(pdf_path: str, out_dir: str, dpi: int | None = None) -> List[str]:
    """Render every page of a PDF to a PNG image. Returns list of image paths."""
    if dpi is None:
        dpi = settings.pdf_dpi
    os.makedirs(out_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)
    paths = []
    for i, page in enumerate(doc):
        if i >= 3:  # Only process the first 3 pages for sandbox speed and non-invoice detection
            break
        pix = page.get_pixmap(matrix=matrix)
        out_path = os.path.join(out_dir, f"page_{i + 1}.png")
        pix.save(out_path)
        paths.append(out_path)
    doc.close()
    return paths


def _laplacian_variance(gray: np.ndarray) -> float:
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def _deskew(gray: np.ndarray) -> Tuple[np.ndarray, float]:
    """Estimate and correct small rotation using minAreaRect on thresholded text mask."""
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thresh > 0))
    if coords.shape[0] < 20:
        return gray, 0.0
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    # Ignore near-zero corrections and implausibly large ones (likely noise)
    if abs(angle) < 0.1 or abs(angle) > 20:
        return gray, 0.0
    (h, w) = gray.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC,
                              borderMode=cv2.BORDER_REPLICATE)
    return rotated, angle


def _correct_orientation(gray: np.ndarray) -> np.ndarray:
    """Heuristic 0/90/180/270 correction using pytesseract OSD if available,
    otherwise falls back to a text-density heuristic (rows vs columns of ink)."""
    try:
        import pytesseract
        osd = pytesseract.image_to_osd(gray)
        rotate = 0
        for line in osd.splitlines():
            if "Rotate:" in line:
                rotate = int(line.split(":")[1].strip())
        if rotate in (90, 180, 270):
            code = {90: cv2.ROTATE_90_COUNTERCLOCKWISE,
                    180: cv2.ROTATE_180,
                    270: cv2.ROTATE_90_CLOCKWISE}[rotate]
            return cv2.rotate(gray, code)
        return gray
    except Exception:
        # No tesseract binary available -> skip orientation correction,
        # PaddleOCR's own angle classifier (use_angle_cls) will still catch most cases.
        return gray


def preprocess_image(image_path: str, out_path: str) -> dict:
    """
    Full pre-processing pipeline for a single page image.
    Returns a dict with quality metadata plus the cleaned image path.
    """
    img = cv2.imread(image_path)
    if img is None:
        # Handle formats OpenCV struggles with via PIL fallback
        pil_img = Image.open(image_path).convert("RGB")
        img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    h, w = img.shape[:2]
    if min(h, w) < MIN_DIMENSION:
        scale = MIN_DIMENSION / min(h, w)
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur_score = _laplacian_variance(gray)
    is_blurry = blur_score < BLUR_THRESHOLD

    gray = _correct_orientation(gray)

    # Denoise
    gray = cv2.fastNlMeansDenoising(gray, h=10)

    # Deskew
    gray, skew_angle = _deskew(gray)

    # Adaptive contrast (CLAHE)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    # Light sharpening to counter blur
    if is_blurry:
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        gray = cv2.filter2D(gray, -1, kernel)

    cv2.imwrite(out_path, gray)

    return {
        "cleaned_path": out_path,
        "blur_score": round(float(blur_score), 2),
        "is_blurry": bool(is_blurry),
        "skew_angle_corrected": round(float(skew_angle), 2),
        "resolution": f"{gray.shape[1]}x{gray.shape[0]}",
        "quality_flag": "low_quality" if is_blurry else "ok",
    }


def preprocess_file(input_path: str, work_dir: str) -> List[dict]:
    """
    Entry point: accepts a PDF or image path, returns a list of per-page
    pre-processing results (one entry for images, one per page for PDFs).
    """
    os.makedirs(work_dir, exist_ok=True)
    ext = os.path.splitext(input_path)[1].lower()

    if ext == ".pdf":
        raw_pages = pdf_to_images(input_path, os.path.join(work_dir, "raw_pages"))
    else:
        raw_pages = [input_path]

    results = []
    for i, page_path in enumerate(raw_pages):
        cleaned_path = os.path.join(work_dir, f"cleaned_{i + 1}.png")
        result = preprocess_image(page_path, cleaned_path)
        result["page_number"] = i + 1
        results.append(result)
    return results
