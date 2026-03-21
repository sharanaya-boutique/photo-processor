"""
process.py — Sharanaya Boutique Photo Processor

Usage:
    python process.py --episode=EP-271
    python process.py --episode=EP-271 --calibrate
    python process.py --episode=EP-271 --verify-only
    python process.py --episode=EP-271 --report
    python process.py --episodes=EP-271,EP-272
    python process.py --all
"""

import argparse
import json
import sys
import warnings
from datetime import datetime, timezone
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
    ep_group = parser.add_mutually_exclusive_group(required=True)
    ep_group.add_argument("--episode", help="Single episode identifier, e.g. EP-271")
    ep_group.add_argument("--episodes", metavar="EP1,EP2,...",
                          help="Comma-separated list of episodes to process in sequence")
    ep_group.add_argument("--all", action="store_true", dest="all_episodes",
                          help="Auto-discover and process all episodes that have both "
                               "docs/<ep>.xlsx and media/<ep>/")
    parser.add_argument("--calibrate", action="store_true",
                        help="Show mask overlay on first image and exit (for calibration)")
    parser.add_argument("--verify-only", action="store_true",
                        help="Scan all saved images in output/<episode>/ and print a barcode pass/fail table")
    parser.add_argument("--report", action="store_true",
                        help="Print the last run's summary for an already-processed episode without reprocessing")
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
# Episode discovery (Phase 5)
# ---------------------------------------------------------------------------

def discover_all_episodes() -> list[str]:
    """Return sorted episode IDs that have both docs/<ep>.xlsx and media/<ep>/."""
    docs_dir = Path("docs")
    media_dir = Path("media")
    episodes = []
    if docs_dir.exists():
        for xlsx_path in sorted(docs_dir.glob("*.xlsx")):
            ep = xlsx_path.stem
            if (media_dir / ep).is_dir():
                episodes.append(ep)
    return episodes


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
# Report / audit trail
# ---------------------------------------------------------------------------

def _report_path(episode: str) -> Path:
    return Path("output") / episode / "report.json"


def load_report(episode: str) -> dict:
    """Load existing report for *episode*, or return a fresh skeleton."""
    path = _report_path(episode)
    if path.exists():
        try:
            with path.open() as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass  # treat a corrupt file as missing
    return {"episode": episode, "runs": []}


def save_report(episode: str, report: dict) -> None:
    """Write *report* to output/<episode>/report.json."""
    path = _report_path(episode)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(report, f, indent=2)


def print_summary_table(run: dict) -> None:
    """Print a human-readable summary table for a single run record."""
    ts = run.get("timestamp", "")
    processed = run.get("processed", 0)
    skipped   = run.get("skipped", 0)
    errors    = run.get("errors", 0)
    images    = run.get("images", [])

    print(f"\n{'='*60}")
    print(f"  Run summary  {ts}")
    print(f"{'='*60}")
    print(f"  Processed : {processed}")
    print(f"  Skipped   : {skipped}")
    print(f"  Errors    : {errors}")
    print(f"{'='*60}")

    if images:
        print(f"\n{'FILE':<40}  {'STATUS':<10}  BARCODE_VERIFIED")
        print("-" * 72)
        for img in images:
            bv = img.get("barcode_verified")
            bv_str = "true" if bv is True else ("false" if bv is False else "null")
            print(f"{img['file']:<40}  {img['status']:<10}  {bv_str}")
        print("-" * 72)

    problem_images = [i for i in images if i["status"] in ("skipped", "error")]
    if problem_images:
        print("\nImages requiring attention:")
        for img in problem_images:
            print(f"  [{img['status'].upper()}] {img['file']}")
    print()


def report_mode(episode: str) -> None:
    """Print the last run's summary without reprocessing."""
    path = _report_path(episode)
    if not path.exists():
        sys.exit(f"ERROR: No report found for episode '{episode}' at {path}")

    report = load_report(episode)
    runs = report.get("runs", [])
    if not runs:
        sys.exit(f"ERROR: Report for '{episode}' contains no runs.")

    print_summary_table(runs[-1])


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
# Per-episode pipeline (Phase 5 refactor — shared by single and batch modes)
# ---------------------------------------------------------------------------

def _run_pipeline(episode: str, lama) -> dict:
    """Run the full processing pipeline for *episode* using *lama*.

    Returns the run_record dict (same structure as Phase 4 report entries).
    Propagates SystemExit on fatal errors (missing files, bad config) so the
    batch driver can catch it without aborting the whole run.
    """
    config = load_episode_config(episode)
    mapping = load_excel(episode)
    images  = find_images(episode)

    processed   = 0
    skipped     = 0
    errors      = 0
    image_records: list[dict] = []

    for img_path in images:
        product_id = extract_product_id(img_path)

        if product_id not in mapping:
            print(f"  SKIP {img_path.name} — no Excel entry for '{product_id}'")
            skipped += 1
            image_records.append({
                "file":             img_path.name,
                "product_id":       product_id,
                "status":           "skipped",
                "barcode_verified": None,
            })
            continue

        row           = mapping[product_id]
        barcode_value = row["product_id"]

        print(f"  Processing {img_path.name} (barcode: {barcode_value})…")
        img = Image.open(img_path).convert("RGB")
        img = remove_watermark(img, lama, config)
        img = embed_barcode(img, barcode_value)
        out_path = save_image(img, episode, img_path)
        barcode_ok = verify_barcode(out_path, barcode_value)
        if not barcode_ok:
            errors += 1
        processed += 1
        image_records.append({
            "file":             img_path.name,
            "product_id":       product_id,
            "status":           "ok" if barcode_ok else "error",
            "barcode_verified": barcode_ok,
        })

    run_record = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "processed": processed,
        "skipped":   skipped,
        "errors":    errors,
        "images":    image_records,
    }

    report = load_report(episode)
    report["runs"].append(run_record)
    save_report(episode, report)
    print(f"\nReport written → {_report_path(episode)}")

    print_summary_table(run_record)
    return run_record


def print_cross_episode_summary(results: list[dict]) -> None:
    """Print aggregated statistics across all processed episodes."""
    total_episodes = len(results)
    total_processed = sum(r.get("processed", 0) for r in results)
    total_skipped   = sum(r.get("skipped",   0) for r in results)
    total_errors    = sum(r.get("errors",    0) for r in results)
    failed_episodes = [r for r in results if r.get("failed")]

    print(f"\n{'='*60}")
    print("  Cross-episode summary")
    print(f"{'='*60}")
    print(f"  Episodes  : {total_episodes}")
    print(f"  Processed : {total_processed}")
    print(f"  Skipped   : {total_skipped}")
    print(f"  Errors    : {total_errors}")
    if failed_episodes:
        print("\n  Episodes with failures:")
        for r in failed_episodes:
            ep      = r.get("episode", "?")
            err_msg = r.get("error", "")
            suffix  = f" — {err_msg}" if err_msg else ""
            print(f"    [{ep}]{suffix}")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()

    # Determine episode list and whether we are in batch mode
    if args.episode:
        episodes = [args.episode]
        is_batch = False
    elif args.episodes:
        episodes = [e.strip() for e in args.episodes.split(",") if e.strip()]
        if not episodes:
            sys.exit("ERROR: --episodes value is empty")
        is_batch = True
    else:  # args.all_episodes is True
        episodes = discover_all_episodes()
        if not episodes:
            sys.exit(
                "ERROR: --all found no episodes "
                "(both docs/<ep>.xlsx and media/<ep>/ must exist for each)"
            )
        print(f"Discovered {len(episodes)} episode(s): {', '.join(episodes)}")
        is_batch = True

    # Single-episode-only special modes (calibrate / verify-only / report)
    if not is_batch:
        episode = episodes[0]
        config  = load_episode_config(episode)

        if args.calibrate:
            calibrate(episode, config)
            return

        if args.verify_only:
            passed = verify_only_mode(episode)
            sys.exit(0 if passed else 1)

        if args.report:
            report_mode(episode)
            return

    # Load SimpleLama once — model is shared across all episodes in a batch
    print("Loading inpainting model (may download on first run)…")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from simple_lama_inpainting import SimpleLama
        lama = SimpleLama()

    if not is_batch:
        # Single episode: preserve existing exit-code behaviour
        run_record = _run_pipeline(episodes[0], lama)
        if run_record["errors"]:
            sys.exit(1)
        return

    # Batch mode: process each episode, collecting results; failures do not abort others
    results: list[dict] = []
    for episode in episodes:
        print(f"\n{'='*60}")
        print(f"  Processing episode: {episode}")
        print(f"{'='*60}")
        try:
            run_record = _run_pipeline(episode, lama)
            results.append({
                "episode":   episode,
                "processed": run_record["processed"],
                "skipped":   run_record["skipped"],
                "errors":    run_record["errors"],
                "failed":    run_record["errors"] > 0,
            })
        except SystemExit as exc:
            msg = " ".join(str(a) for a in exc.args).strip() if exc.args else ""
            print(f"\nFAILED: {msg}")
            results.append({
                "episode":   episode,
                "processed": 0,
                "skipped":   0,
                "errors":    1,
                "failed":    True,
                "error":     msg,
            })
        except Exception as exc:
            print(f"\nFAILED: {exc}")
            results.append({
                "episode":   episode,
                "processed": 0,
                "skipped":   0,
                "errors":    1,
                "failed":    True,
                "error":     str(exc),
            })

    print_cross_episode_summary(results)

    if any(r["failed"] for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
