"""
process.py — Sharanaya Boutique Photo Processor

Usage:
    python process.py --episode=EP-271
    python process.py --episode=EP-271 --calibrate
    python process.py --episode=EP-271 --verify-only
"""

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import openpyxl
from PIL import Image

# Watermark mask region (relative to image dimensions) — module-level defaults
MASK_Y_START = 0.75
MASK_Y_END   = 0.88
MASK_X_START = 0.30
MASK_X_END   = 0.70

CONFIG_DIR = Path("config")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="Remove watermark and embed barcode on product photos.")
    parser.add_argument("--episode", required=True, help="Episode identifier, e.g. EP-271")
    parser.add_argument("--calibrate", action="store_true",
                        help="Show mask overlay on first image and exit (for calibration)")
    parser.add_argument("--verify-only", action="store_true",
                        help="Scan all saved images in output/<episode>/ and print a barcode pass/fail table")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Per-episode mask config
# ---------------------------------------------------------------------------

def _defaults() -> dict:
    return {
        "mask_y_start": MASK_Y_START,
        "mask_y_end":   MASK_Y_END,
        "mask_x_start": MASK_X_START,
        "mask_x_end":   MASK_X_END,
    }


def validate_config(config: dict, source=None) -> None:
    """Validate mask values are floats in [0, 1] and each start < end."""
    label = f" in {source}" if source else ""
    for key in ("mask_y_start", "mask_y_end", "mask_x_start", "mask_x_end"):
        val = config[key]
        if not isinstance(val, (int, float)) or not (0 <= val <= 1):
            sys.exit(f"ERROR: '{key}' must be a number between 0 and 1{label}, got {val!r}")
    for start_key, end_key in (("mask_y_start", "mask_y_end"), ("mask_x_start", "mask_x_end")):
        if config[start_key] >= config[end_key]:
            sys.exit(f"ERROR: '{start_key}' must be less than '{end_key}'{label}")


def load_episode_config(episode: str) -> dict:
    """Return mask config for *episode*, falling back to module-level defaults."""
    config_path = CONFIG_DIR / f"{episode}.json"
    if not config_path.exists():
        return _defaults()

    try:
        with config_path.open() as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        sys.exit(f"ERROR: Invalid JSON in {config_path}: {e}")

    known_keys = set(_defaults())
    config = _defaults()
    for k, v in data.items():
        if k in known_keys:
            config[k] = v
    validate_config(config, config_path)
    print(f"Loaded mask config from {config_path}")
    return config


# ---------------------------------------------------------------------------
# Excel mapping
# ---------------------------------------------------------------------------

def load_excel(episode: str) -> dict:
    """Return {product_id: {sln, product_id, ...}} from docs/{episode}.xlsx."""
    path = Path("docs") / f"{episode}.xlsx"
    if not path.exists():
        sys.exit(f"ERROR: Excel file not found: {path}")

    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active

    mapping = {}
    for row in ws.iter_rows(min_row=2, values_only=True):  # skip header row
        if not row or len(row) < 9:
            continue
        episode_col, sln, bill_done, seq, price1, price2, fabric, color, product_id = row[:9]
        if not product_id:
            continue
        product_id = str(product_id).strip()
        mapping[product_id] = {
            "episode":    episode_col,
            "sln":        sln,
            "product_id": product_id,
            "price":      price1,
            "fabric":     fabric,
            "color":      color,
        }

    if not mapping:
        sys.exit(f"ERROR: No product rows found in {path}")

    print(f"Loaded {len(mapping)} product(s) from {path}")
    return mapping


# ---------------------------------------------------------------------------
# Image discovery
# ---------------------------------------------------------------------------

def find_images(episode: str) -> list:
    """Return sorted list of .jpg Paths under media/{episode}/."""
    media_dir = Path("media") / episode
    if not media_dir.exists():
        sys.exit(f"ERROR: Media directory not found: {media_dir}")

    images = sorted(media_dir.glob("*.jpg")) + sorted(media_dir.glob("*.JPG"))
    if not images:
        sys.exit(f"ERROR: No .jpg images found in {media_dir}")

    print(f"Found {len(images)} image(s) in {media_dir}")
    return images


def extract_product_id(path: Path) -> str:
    """'B000055923 A.jpg' → 'B000055923'"""
    return path.stem.split(" ")[0]


# ---------------------------------------------------------------------------
# Watermark removal
# ---------------------------------------------------------------------------

def build_mask(img: Image.Image, config: dict) -> Image.Image:
    """Create a white-on-black PIL mask for the watermark region."""
    w, h = img.size
    mask = Image.new("L", (w, h), 0)  # black background

    y0 = int(h * config["mask_y_start"])
    y1 = int(h * config["mask_y_end"])
    x0 = int(w * config["mask_x_start"])
    x1 = int(w * config["mask_x_end"])

    mask_arr = np.array(mask)
    mask_arr[y0:y1, x0:x1] = 255
    return Image.fromarray(mask_arr)


def remove_watermark(img: Image.Image, lama, config: dict) -> Image.Image:
    """Inpaint the watermark region using SimpleLama."""
    mask = build_mask(img, config)
    result = lama(img, mask)
    return result


# ---------------------------------------------------------------------------
# Barcode embedding
# ---------------------------------------------------------------------------

def embed_barcode(img: Image.Image, value: str) -> Image.Image:
    """Generate a Code 128 barcode and paste it into the bottom-right corner."""
    import barcode
    from barcode.writer import ImageWriter
    import io

    # Generate barcode to an in-memory PNG
    code128_class = barcode.get_barcode_class("code128")
    writer = ImageWriter()
    writer.set_options({
        "module_height": 8.0,
        "font_size":     6,
        "text_distance": 2.0,
        "quiet_zone":    2.0,
    })

    buffer = io.BytesIO()
    code128_class(value, writer=writer).write(buffer)
    buffer.seek(0)
    barcode_img = Image.open(buffer).convert("RGB")

    # Resize barcode to ~20% of image width
    img_w, img_h = img.size
    target_w = max(120, int(img_w * 0.20))
    ratio = target_w / barcode_img.width
    target_h = int(barcode_img.height * ratio)
    barcode_img = barcode_img.resize((target_w, target_h), Image.LANCZOS)

    # Add white padding around barcode
    pad = 6
    padded_w = barcode_img.width + pad * 2
    padded_h = barcode_img.height + pad * 2
    padded = Image.new("RGB", (padded_w, padded_h), (255, 255, 255))
    padded.paste(barcode_img, (pad, pad))

    # Paste at bottom-right, 10px from edges
    margin = 10
    x = img_w - padded_w - margin
    y = img_h - padded_h - margin

    result = img.copy()
    result.paste(padded, (x, y))
    return result


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def save_image(img: Image.Image, episode: str, original_path: Path) -> Path:
    out_dir = Path("output") / episode
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / original_path.name
    img.save(out_path, "JPEG", quality=95)
    print(f"  Saved → {out_path}")
    return out_path


# ---------------------------------------------------------------------------
# Barcode verification
# ---------------------------------------------------------------------------

def decode_barcode(image_path: Path) -> str | None:
    """Return the first decoded barcode string from image_path, or None."""
    from pyzbar.pyzbar import decode as pyzbar_decode
    img = Image.open(image_path).convert("RGB")
    results = pyzbar_decode(img)
    if results:
        return results[0].data.decode("utf-8")
    return None


def verify_barcode(out_path: Path, expected_value: str) -> bool:
    """Decode barcode from out_path and compare against expected_value.

    Returns True on match, False on mismatch or decode failure.
    Prints an ERROR line when the barcode does not match.
    """
    decoded = decode_barcode(out_path)
    if decoded != expected_value:
        print(f"ERROR: barcode mismatch for {out_path}  "
              f"(expected={expected_value!r}, got={decoded!r})")
        return False
    return True


def verify_only_mode(episode: str) -> bool:
    """Scan all images in output/<episode>/ and print a pass/fail table.

    Returns True if every barcode passed, False if any failed.
    """
    out_dir = Path("output") / episode
    if not out_dir.exists():
        sys.exit(f"ERROR: Output directory not found: {out_dir}")

    images = sorted(out_dir.glob("*.jpg")) + sorted(out_dir.glob("*.JPG"))
    if not images:
        sys.exit(f"ERROR: No .jpg images found in {out_dir}")

    print(f"\nVerifying {len(images)} image(s) in {out_dir}\n")
    print(f"{'FILE':<40}  {'EXPECTED':<20}  {'DECODED':<20}  STATUS")
    print("-" * 100)

    all_passed = True
    for img_path in images:
        expected = extract_product_id(img_path)
        decoded  = decode_barcode(img_path)
        passed   = decoded == expected
        status   = "PASS" if passed else "FAIL"
        if not passed:
            all_passed = False
        print(f"{img_path.name:<40}  {expected:<20}  {str(decoded):<20}  {status}")

    print("-" * 100)
    overall = "ALL PASSED" if all_passed else "FAILURES DETECTED"
    print(f"\nResult: {overall}\n")
    return all_passed


# ---------------------------------------------------------------------------
# Calibration helper
# ---------------------------------------------------------------------------

def calibrate(episode: str, config: dict):
    """Overlay the mask region on the first image, then prompt to save config."""
    images = find_images(episode)
    img = Image.open(images[0]).convert("RGB")
    mask = build_mask(img, config)

    # Tint the masked area red so it's easy to see
    overlay = img.copy()
    mask_arr = np.array(mask)
    img_arr  = np.array(overlay)
    img_arr[mask_arr == 255, 0] = 255   # red channel max
    img_arr[mask_arr == 255, 1] = 0
    img_arr[mask_arr == 255, 2] = 0

    preview = Image.fromarray(img_arr)
    w, h = preview.size
    # Scale down for display if large
    if w > 1200:
        scale = 1200 / w
        preview = preview.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    print(f"Calibration preview for: {images[0].name}")
    print(f"  Image size : {w} x {h}")
    print(f"  Mask region: y={config['mask_y_start']*100:.0f}%–{config['mask_y_end']*100:.0f}%  "
          f"x={config['mask_x_start']*100:.0f}%–{config['mask_x_end']*100:.0f}%")
    preview.show()

    answer = input("Save these mask coordinates for this episode? [y/N] ").strip().lower()
    if answer == "y":
        CONFIG_DIR.mkdir(exist_ok=True)
        config_path = CONFIG_DIR / f"{episode}.json"
        with config_path.open("w") as f:
            json.dump(config, f, indent=2)
        print(f"Saved → {config_path}")
    else:
        print("Not saved. Adjust MASK_* constants in process.py and re-run --calibrate.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    episode = args.episode
    config = load_episode_config(episode)

    if args.calibrate:
        calibrate(episode, config)
        return

    if args.verify_only:
        passed = verify_only_mode(episode)
        sys.exit(0 if passed else 1)

    mapping = load_excel(episode)
    images  = find_images(episode)

    # Load SimpleLama once (model download on first run)
    print("Loading inpainting model (may download on first run)…")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from simple_lama_inpainting import SimpleLama
        lama = SimpleLama()

    processed = 0
    skipped   = 0
    errors    = 0

    for img_path in images:
        product_id = extract_product_id(img_path)

        if product_id not in mapping:
            print(f"  SKIP {img_path.name} — no Excel entry for '{product_id}'")
            skipped += 1
            continue

        row           = mapping[product_id]
        barcode_value = row["product_id"]

        print(f"  Processing {img_path.name} (barcode: {barcode_value})…")
        img = Image.open(img_path).convert("RGB")
        img = remove_watermark(img, lama, config)
        img = embed_barcode(img, barcode_value)
        out_path = save_image(img, episode, img_path)
        if not verify_barcode(out_path, barcode_value):
            errors += 1
        processed += 1

    print(f"\nDone. {processed} processed, {skipped} skipped, {errors} barcode error(s).")
    if skipped:
        print("Skipped images had no matching product ID in the Excel file.")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
