# Plan: Sharanaya Boutique Photo Processor

> Source: Implementation plan confirmed in session 2026-03-21

---

## Architectural decisions

Durable decisions that apply across all phases:

- **CLI entry point**: `python process.py --episode=<ID>` — episode is always the primary key
- **Source of truth**: `docs/<episode>.xlsx`, col I (Product ID) is the authoritative barcode value; filenames are derived from it, not the other way around
- **Image filename convention**: `{product_id} {variant}.jpg` — product ID is everything before the first space
- **Paths**:
  - Input:  `media/<episode>/*.jpg`
  - Mapping: `docs/<episode>.xlsx`
  - Output: `output/<episode>/` (mirrors input filenames, originals untouched)
- **Watermark removal**: AI inpainting via `simple-lama-inpainting` over a fixed relative mask region
- **Barcode type**: Code 128 linear barcode, value = product ID from Excel
- **Barcode placement**: bottom-right corner, white padded background, 10 px margin from edges, ~20% of image width

---

## Phase 1: Core Pipeline ✅ IMPLEMENTED

**User stories**:
- As an operator, I can run a single command per episode and get all product photos watermark-removed and barcode-stamped.

### What to build

End-to-end pipeline for one episode: read the Excel mapping, glob input images, for each image remove the watermark using AI inpainting over a fixed mid-lower mask region, embed a Code 128 barcode (from Excel col I) in the bottom-right corner, and write results to `output/<episode>/`. Images with no matching Excel row are skipped with a warning.

Include a `--calibrate` flag that overlays the mask region in red on the first image and opens it for visual inspection — allows tuning the `MASK_*` constants before a full run.

### Acceptance criteria

- [x] `python process.py --episode=EP-271` processes all `.jpg` files in `media/EP-271/`
- [x] Output lands in `output/EP-271/` with original filenames; source files unchanged
- [x] Watermark region (mid-lower strip) is inpainted cleanly
- [x] Code 128 barcode in bottom-right reads back as the product ID (e.g. `B000055923`)
- [x] Images with no Excel row are skipped with a printed warning; processing continues
- [x] `--calibrate` displays a red overlay of the mask region on the first image and exits

---

## Phase 2: Per-Episode Mask Configuration ✅ IMPLEMENTED

**User stories**:
- As an operator, I can adjust the watermark mask for a specific episode without changing the code, because watermark placement shifts slightly between episodes.

### What to build

Replace the hardcoded `MASK_*` constants with a per-episode override system. Add a `config/` directory where a `<episode>.json` file can override mask coordinates for that episode. If no config file exists, fall back to the global defaults. Extend `--calibrate` to write the current mask values into `config/<episode>.json` after the user confirms the overlay looks correct (prompt Y/N in terminal).

```
config/
  EP-271.json       ← {"mask_y_start": 0.75, "mask_y_end": 0.88, ...}
  EP-272.json       ← episode-specific override
```

### Acceptance criteria

- [x] If `config/<episode>.json` exists, its mask values are used instead of the module-level defaults
- [x] `--calibrate` prompts the user to save the displayed mask coordinates and writes `config/<episode>.json` on confirmation
- [x] Missing config file falls back to defaults without error
- [x] Config file values are validated (0–1 range, start < end); bad values print a clear error

---

## Phase 3: Barcode Readability Verification ✅ IMPLEMENTED

**User stories**:
- As an operator, I want confirmation that the embedded barcodes are actually scannable, not just visually present.

### What to build

After saving each output image, decode the barcode from the saved file using `pyzbar` (or `opencv` QR/barcode detector) and compare the decoded value against the expected product ID. Report mismatches as errors. Add a `--verify-only` flag that reads already-processed output images and reports barcode scan results without re-processing.

### Acceptance criteria

- [x] Each saved image is scanned immediately after writing; a mismatch prints `ERROR: barcode mismatch for <file>`
- [x] `--verify-only --episode=EP-271` scans all files in `output/EP-271/` and prints a pass/fail table
- [x] Exit code is non-zero if any barcode failed to scan or mismatched
- [x] `requirements.txt` updated with `pyzbar` (and system note about `libzbar` native dependency)

---

## Phase 4: Run Report & Audit Trail ✅ IMPLEMENTED

**User stories**:
- As an operator, I want a machine-readable summary of each processing run so I can track which images were processed, which were skipped, and catch Excel/image mismatches.

### What to build

After each run, write a JSON report to `output/<episode>/report.json` summarising the run: timestamp, episode, counts (processed / skipped / errors), and a per-image record (filename, product_id, barcode_value, status, barcode_verified). Also print a human-readable table to stdout at the end. The report accumulates across runs (new run appends to a `runs` list).

```json
{
  "episode": "EP-271",
  "runs": [
    {
      "timestamp": "2026-03-21T14:32:00",
      "processed": 26,
      "skipped": 0,
      "errors": 0,
      "images": [
        {"file": "B000055923 A.jpg", "product_id": "B000055923", "status": "ok", "barcode_verified": true},
        ...
      ]
    }
  ]
}
```

### Acceptance criteria

- [x] `output/<episode>/report.json` is written (or appended) at the end of every run
- [x] Report includes per-image status: `ok`, `skipped` (no Excel row), or `error` (inpainting/barcode failure)
- [x] Stdout summary table shows totals and lists any skipped/errored images by name
- [x] `--report` flag prints the last run's summary for an already-processed episode without reprocessing

---

## Phase 5: Multi-Episode & Batch Processing ✅ IMPLEMENTED

**User stories**:
- As an operator, I can process multiple episodes in one command, or all episodes that have an Excel file, to prepare an entire season's catalog in one go.

### What to build

Add `--episodes=EP-271,EP-272` (comma-separated list) and `--all` (processes every episode that has both a `docs/<episode>.xlsx` and a `media/<episode>/` directory). Episodes are processed sequentially. Print a cross-episode summary at the end. Reuse the per-episode report from Phase 4.

### Acceptance criteria

- [x] `--episodes=EP-271,EP-272` processes both episodes in order
- [x] `--all` discovers all episode pairs (docs + media both present) and processes them
- [x] `--episode` and `--all`/`--episodes` are mutually exclusive; bad combinations print a usage error
- [x] Final summary prints totals across all episodes: N episodes, M images processed, K skipped
- [x] One episode failing (e.g. missing Excel file) does not abort other episodes; errors are collected and shown at the end
