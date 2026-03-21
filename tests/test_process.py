"""Lightweight CI tests — no real media or Excel files required."""

import numpy as np
from pathlib import Path
from PIL import Image

from process import extract_product_id, build_mask, MASK_Y_START, MASK_Y_END, MASK_X_START, MASK_X_END


# ---------------------------------------------------------------------------
# extract_product_id
# ---------------------------------------------------------------------------

def test_extract_product_id_variant_a():
    assert extract_product_id(Path("B000055923 A.jpg")) == "B000055923"


def test_extract_product_id_variant_multi_letter():
    assert extract_product_id(Path("F000068463 E.jpg")) == "F000068463"


def test_extract_product_id_no_variant():
    # stem with no space — entire stem is the product id
    assert extract_product_id(Path("B000055923.jpg")) == "B000055923"


# ---------------------------------------------------------------------------
# build_mask
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "mask_y_start": MASK_Y_START,
    "mask_y_end":   MASK_Y_END,
    "mask_x_start": MASK_X_START,
    "mask_x_end":   MASK_X_END,
}


def test_build_mask_shape():
    img = Image.new("RGB", (100, 200), color=(255, 255, 255))
    mask = build_mask(img, DEFAULT_CONFIG)
    assert mask.size == (100, 200)


def test_build_mask_region():
    w, h = 100, 200
    img = Image.new("RGB", (w, h), color=(255, 255, 255))
    mask = build_mask(img, DEFAULT_CONFIG)
    arr = np.array(mask)

    y0 = int(h * MASK_Y_START)
    y1 = int(h * MASK_Y_END)
    x0 = int(w * MASK_X_START)
    x1 = int(w * MASK_X_END)

    # Inside the mask region must be white (255)
    assert np.all(arr[y0:y1, x0:x1] == 255), "Mask region should be 255"

    # Corners must be black (0)
    assert arr[0, 0] == 0, "Top-left corner should be 0"
    assert arr[h - 1, w - 1] == 0, "Bottom-right corner should be 0"
