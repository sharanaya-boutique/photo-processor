# Photo Processor — Project Status

**Last updated:** 2026-03-21
**Closes:** [#1 — core photo processing pipeline](https://github.com/sharanaya-boutique/photo-processor/issues/1)

---

## What this project does

Batch-processes per-episode product photos for Sharanaya Boutique:
1. Reads `docs/<episode>.xlsx` to map product barcodes (col I) to images
2. Removes the watermark burned into the mid-lower area of each photo using AI inpainting
3. Embeds a Code 128 barcode (product ID from Excel) in the bottom-right corner
4. Saves results to `output/<episode>/` — originals in `media/<episode>/` are never touched

---

## Current state

**All 5 phases implemented.** The tool is fully functional.

### Files

| File | Purpose |
|---|---|
| `process.py` | Main script (~641 lines) |
| `requirements.txt` | Runtime Python dependencies (6 packages) |
| `requirements-ci.txt` | CI-only dependencies (excludes PyTorch/heavy deps) |
| `VERSION` | Current release version (e.g. `0.1`) |
| `tests/test_process.py` | Lightweight pytest tests for CI |
| `.github/workflows/verify.yml` | CI: lint + test on every PR to master |
| `.github/workflows/release.yml` | CI: version bump + git tag on every master merge |
| `plans/photo-processor.md` | Phased implementation plan |

---

## Setup

### Virtual environment

```bash
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Activate (macOS / Linux)
source .venv/bin/activate
```

### Install dependencies

```bash
# Runtime (includes AI inpainting model — downloads ~200 MB on first run)
pip install -r requirements.txt

# CI / development only (no PyTorch, fast install)
pip install -r requirements-ci.txt
```

---

## How to run

```bash
# Verify mask position before first run on a new episode (opens image with red overlay)
python process.py --episode=EP-271 --calibrate

# Full processing run — single episode
python process.py --episode=EP-271

# Multiple specific episodes
python process.py --episodes=EP-271,EP-272

# All episodes found in media/
python process.py --all

# Verify barcode readability of already-processed output (no re-processing)
python process.py --episode=EP-271 --verify-only

# Generate a run report (writes output/<episode>/report.json)
python process.py --episode=EP-271 --report
```

### Input / output

```
media/EP-271/B000055923 A.jpg   →   output/EP-271/B000055923 A.jpg
```

---

## CI workflow

| Trigger | Job | What it does |
|---|---|---|
| PR opened/updated → `master` | **Verify** | `ruff check` + `pytest tests/` |
| PR merged → `master` | **Release** | Bumps `VERSION` (e.g. `0.1` → `0.2`), commits, pushes tag `v0.2` |

The **Release** job uses `GITHUB_TOKEN` with `contents: write`. The bot commit does not re-trigger the release workflow (GitHub Actions safety behaviour).

---

## Key design decisions

| Decision | Choice |
|---|---|
| Watermark removal | AI inpainting via `simple-lama-inpainting` over a fixed relative mask |
| Mask region | `MASK_Y_START/END = 0.75–0.88`, `MASK_X_START/END = 0.30–0.70` (overridable via `config/<episode>.json`) |
| Barcode type | Code 128 linear |
| Barcode value | Excel col I (Product ID) — e.g. `B000055923` |
| Barcode placement | Bottom-right, ~20% image width, white padded, 10 px margin |
| Excel structure | Row 1 = header; col I = Product ID (join key); skip rows where col I is empty |
| Image filename pattern | `{product_id} {variant}.jpg` — product ID = everything before first space |
| Per-episode mask | `config/<episode>.json` overrides module-level `MASK_*` constants |
| Barcode verification | `pyzbar` scan of saved output; `--verify-only` skips re-processing |
| Run report | `output/<episode>/report.json` written when `--report` flag is used |
| Versioning | Flat `VERSION` file, `v0.MINOR` scheme, auto-bumped by CI on every master merge |

---

## Calibration note

The watermark mask constants **must be visually confirmed** for each new episode before
the first production run. Run `--calibrate` and check that the red overlay covers the
watermark text. Per-episode overrides are saved to `config/<episode>.json`.

---

## Dependencies

```
# requirements.txt (runtime)
openpyxl               # Excel reading
Pillow                 # Image I/O and manipulation
python-barcode[images] # Code 128 barcode generation
simple-lama-inpainting # AI inpainting (downloads ~200 MB model on first run)
opencv-python          # Image array operations
numpy                  # Mask construction

# requirements-ci.txt (CI / development)
openpyxl
Pillow
python-barcode[images]
numpy
ruff                   # Linter
pytest                 # Test runner
```
