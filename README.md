# Photo Processor — Sharanaya Boutique

Batch-processes per-episode product photos:

1. Reads `docs/<episode>.xlsx` to map product IDs (col I) to image files
2. Removes the watermark from each photo using AI inpainting
3. Embeds a scannable Code 128 barcode (product ID) in the bottom-right corner
4. Writes results to `output/<episode>/` — originals in `media/<episode>/` are never touched

---

## Requirements

- Python 3.11+
- On Linux/macOS, `libzbar` is required for barcode verification:
  ```bash
  # Ubuntu / Debian
  sudo apt-get install libzbar0

  # macOS
  brew install zbar
  ```

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/sharanaya-boutique/photo-processor.git
cd photo-processor
```

### 2. Create the virtual environment

```bash
python -m venv .venv
```

### 3. Activate the virtual environment

**Windows — Git Bash**
```bash
source .venv/Scripts/activate
```

**Windows — PowerShell**
```powershell
.venv\Scripts\Activate.ps1
```

**Windows — Command Prompt**
```bat
.venv\Scripts\activate.bat
```

**macOS / Linux**
```bash
source .venv/bin/activate
```

Your prompt will change to show `(.venv)` confirming the environment is active. All commands from this point must be run inside the activated environment.

> **Note:** When creating the venv on Windows you may see `Could not find platform independent libraries <prefix>`. This is a harmless warning — the environment is created successfully.

### 4. Install Python dependencies

```bash
pip install -r requirements.txt
```

> `simple-lama-inpainting` downloads a ~200 MB AI model on first run. Subsequent runs use the cached model.

### 5. Verify the install

```bash
python process.py --help
```

You should see the full list of CLI flags with no import errors.

---

### Activating the environment in future sessions

Every time you open a new terminal, activate the environment before running the tool:

**Windows — Git Bash**
```bash
source .venv/Scripts/activate
```

**Windows — PowerShell**
```powershell
.venv\Scripts\Activate.ps1
```

**macOS / Linux**
```bash
source .venv/bin/activate
```

To deactivate when done:
```bash
deactivate
```

---

## Directory layout

```
photo-processor/
├── process.py              # Main script
├── requirements.txt        # Runtime dependencies
├── requirements-ci.txt     # CI-only dependencies (no PyTorch)
├── VERSION                 # Current release version
├── docs/                   # Excel files — docs/<episode>.xlsx  (gitignored)
├── media/                  # Source images — media/<episode>/*.jpg  (gitignored)
├── output/                 # Processed output — output/<episode>/  (gitignored)
├── config/                 # Per-episode mask overrides — config/<episode>.json
└── tests/                  # Pytest tests
```

---

## Usage

### Single episode

```bash
python process.py --episode=EP-271
```

### Multiple episodes

```bash
python process.py --episodes=EP-271,EP-272
```

### All episodes (auto-discover)

```bash
python process.py --all
```

Processes every episode that has both a `docs/<episode>.xlsx` and a `media/<episode>/` directory.

### Calibrate mask position

```bash
python process.py --episode=EP-271 --calibrate
```

Overlays the inpainting mask in red on the first image for visual inspection. Prompts to save the coordinates to `config/EP-271.json`.

Run this before the first production run on any new episode — watermark placement shifts slightly between episodes.

### Verify barcode readability

```bash
python process.py --episode=EP-271 --verify-only
```

Scans barcodes in already-processed `output/EP-271/` images and prints a pass/fail table. Does not re-process images. Exits non-zero if any barcode fails.

### View run report

```bash
python process.py --episode=EP-271 --report
```

Prints the last run's summary from `output/EP-271/report.json`.

---

## Per-episode mask config

If the watermark position differs from the default, save a per-episode config:

```json
// config/EP-272.json
{
  "mask_y_start": 0.76,
  "mask_y_end": 0.89,
  "mask_x_start": 0.28,
  "mask_x_end": 0.72
}
```

All values are fractional (0–1) relative to image dimensions. If the file is absent, global defaults in `process.py` are used.

---

## Run report

Each processing run appends to `output/<episode>/report.json`:

```json
{
  "episode": "EP-271",
  "runs": [
    {
      "timestamp": "2026-03-21T14:32:00Z",
      "processed": 26,
      "skipped": 0,
      "errors": 0,
      "images": [
        {
          "file": "B000055923 A.jpg",
          "product_id": "B000055923",
          "status": "ok",
          "barcode_verified": true
        }
      ]
    }
  ]
}
```

---

## CI

| Trigger | Job | What it does |
|---|---|---|
| PR → `master` | **Verify** | `ruff check` + `pytest tests/` |
| Merge → `master` | **Release** | Bumps `VERSION`, commits, pushes git tag (e.g. `v0.2`) |

---

## Development

```bash
# Install CI/dev dependencies (no PyTorch — fast)
pip install -r requirements-ci.txt

# Run linter
ruff check process.py

# Run tests
pytest tests/ -v
```

---

## Excel file format

| Col | Field | Notes |
|---|---|---|
| A | Episode | e.g. `EP-271` |
| B | SLN | — |
| C | Bill Done | — |
| D | Seq | — |
| E | Price 1 | — |
| F | Price 2 | — |
| G | Fabric | — |
| H | Color | — |
| I | **Product ID** | Barcode value and image filename prefix |

Row 1 is the header. Rows where col I is empty are skipped.

---

## Image filename convention

```
{product_id} {variant}.jpg
```

Examples: `B000055923 A.jpg`, `F000068463 C.jpg`

The product ID is everything before the first space. It must match col I in the Excel file.
