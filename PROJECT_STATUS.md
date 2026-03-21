# Photo Processor — Project Status

**Last updated:** 2026-03-21

---

## What this project does

Batch-processes per-episode product photos for Sharanaya Boutique:
1. Reads `docs/<episode>.xlsx` to map product barcodes (col I) to images
2. Removes the watermark burned into the mid-lower area of each photo using AI inpainting
3. Embeds a Code 128 barcode (product ID from Excel) in the bottom-right corner
4. Saves results to `output/<episode>/` — originals in `media/<episode>/` are never touched

---

## Current state

**Phase 1 (Core Pipeline) is implemented.** The tool is functional end-to-end.

### Files created
| File | Purpose |
|---|---|
| `process.py` | Main script (~200 lines) |
| `requirements.txt` | 6 Python dependencies |
| `plans/photo-processor.md` | Phased implementation plan |

### How to run
```bash
pip install -r requirements.txt

# Verify mask position before first run (opens image with red overlay)
python process.py --episode=EP-271 --calibrate

# Full processing run
python process.py --episode=EP-271
```

### Input / output
```
media/EP-271/B000055923 A.jpg   →   output/EP-271/B000055923 A.jpg
```

---

## Key design decisions

| Decision | Choice |
|---|---|
| Watermark removal | AI inpainting via `simple-lama-inpainting` over a fixed relative mask |
| Mask region | `MASK_Y_START/END = 0.75–0.88`, `MASK_X_START/END = 0.30–0.70` (tunable constants at top of `process.py`) |
| Barcode type | Code 128 linear |
| Barcode value | Excel col I (Product ID) — e.g. `B000055923` |
| Barcode placement | Bottom-right, ~20% image width, white padded, 10 px margin |
| Excel structure | Row 1 = header; col I = Product ID (join key); skip rows where col I is empty |
| Image filename pattern | `{product_id} {variant}.jpg` — product ID = everything before first space |

---

## Phases remaining (see `plans/photo-processor.md` for details)

| Phase | Title | Summary |
|---|---|---|
| 2 | Per-Episode Mask Config | Move mask coords out of code → `config/<episode>.json` |
| 3 | Barcode Readability Verification | Scan saved barcodes with `pyzbar`; `--verify-only` flag |
| 4 | Run Report & Audit Trail | Write `output/<episode>/report.json` after each run |
| 5 | Multi-Episode Batch Processing | `--all` and `--episodes=EP-271,EP-272` flags |

---

## Known calibration step

The watermark mask constants **must be visually confirmed** for each new episode before
the first production run. Run `--calibrate` and check that the red overlay covers the
watermark text. Adjust `MASK_*` constants at the top of `process.py` if needed.

Once Phase 2 is built, this will be saved per-episode to `config/<episode>.json` instead.

---

## Dependencies

```
openpyxl              # Excel reading
Pillow                # Image I/O and manipulation
python-barcode[images] # Code 128 barcode generation
simple-lama-inpainting # AI inpainting (downloads model on first run)
opencv-python         # Image array operations
numpy                 # Mask construction
```

> `simple-lama-inpainting` downloads a ~200 MB model on first run. Subsequent runs use the cached model.
