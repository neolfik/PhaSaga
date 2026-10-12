# Phase Association Analysis

> **Note on AI assistance:** Parts of this project were developed with the help of AI
> tooling. AI was used to speed up development and to make the scripts more efficient
> and faster. All scientific logic, requirements and final validation remain the
> responsibility of the project authors.

A desktop tool for processing SEM/EDS reports, clustering measured compositions,
associating them with theoretical phases, and exporting results for further
visualisation (e.g. ROLOG ternary diagrams).

---

## Overview

The program reads a folder of SEM `.docx` reports, groups them by
**system / temperature / sample**, extracts and normalises the measured
compositions, builds per-sample Excel workbooks, lets the user interactively
cluster the data on a ternary diagram, and finally associates each cluster with a
theoretical phase. Results are exported both as Excel workbooks and as `.exp`
files for ternary plotting.

It is organised around three workflows, selectable from the start menu:

1. **New Analysis** – process a folder of new SEM reports end-to-end.
2. **Phase Reassociation** – edit the phase list and phase associations of an
   already processed system without re-reading the raw reports.
3. **XRD Assignment** – mark which samples have XRD data available and get
   recommendations on which phases still need XRD confirmation.

---

## Requirements

- **Python 3.10+** (developed and tested with Python 3.14)
- **Tkinter** (usually shipped with Python; on Linux install `python3-tk`)

Python packages:

| Package | Purpose |
|---------|---------|
| `numpy` | numerical operations |
| `pandas` | Excel/CSV handling |
| `openpyxl` | reading/writing `.xlsx` files and embedding images |
| `scikit-learn` | DBSCAN clustering and silhouette scoring |
| `matplotlib` | ternary plots and image selection |
| `Pillow` | image loading/validation |
| `docx2python` | extracting tables and text from `.docx` reports |
| `termcolor` | coloured console output |

Install with:

```bash
pip install numpy pandas openpyxl scikit-learn matplotlib Pillow docx2python termcolor
```

---

## Installation

```bash
git clone https://github.com/neolfik/PhaSaga.git
cd PhaSaga
pip install numpy pandas openpyxl scikit-learn matplotlib Pillow docx2python termcolor
python main.py
```

> The program reads `elements.csv`, `student.csv` and `config.json` from the
> directory it is launched in, so run it from inside the `prog/` folder.

---

## Input files

| File | Description |
|------|-------------|
| `elements.csv` | Element database (`Short`, `Name`, `Weight`). Used for weight→atomic conversion and filename validation. |
| `student.csv` | Student-t coefficients used for uncertainty/outlier calculations. |
| `config.json` | Runtime configuration (normalisation and image embedding). |
| `master_phases_template.json` | Template for the local master phase database. Copy it to `master_phases.json` to start. |

### SEM report naming convention

Reports must be named:

```
<System>_<temperature>_<sample>.docx
```

- `<System>` – element symbols, e.g. `InLaNi`, `AlMgSn`, `InSbZn`
- `<temperature>` – digits or `AC`, e.g. `500`, `AC`
- `<sample>` – sample number followed by a measurement letter, e.g. `1a`, `2c`

The letter **`a`** is reserved for the overall composition of the sample; letters
`b`, `c`, … are individual measurements used for clustering.

Example folder:

```
reports_folder/
  InLaNi_500_1a.docx
  InLaNi_500_1b.docx
  InLaNi_500_1c.docx
  InLaNi_500_2a.docx
  ...
```

An optional `export/` folder produced by the Phenom software (CSV/TIFF) is also
detected and merged when present.

---

## Usage

Run the program:

```bash
python main.py
```

### 1. New Analysis

1. Choose **Select Folder…** and pick the folder containing the `.docx` reports.
2. For each new system, a **phase list builder** window opens. Enter the
   theoretical phases (one per line or comma separated). Phase names are
   validated against the system elements; the list is stored in
   `phases_<System>.txt`.
3. For each sample the interactive **clustering window** opens. Choose the
   suggested clustering (2 or 3 clusters), or draw a custom lasso selection.
   Each cluster is then associated with a phase, closest candidates are suggested
   automatically.
4. Results (Excel workbooks, `.exp` files, ternary diagrams) are written to the
   output folder structure described below.

### 2. Phase Reassociation

Re-runs phase association for an already processed system:

- Select one system/temperature.
- Optionally edit the phase list (`phases_<System>.txt`).
- Edit the phase associated with each cluster using the phase table.
- The `.exp` and phase-prediction files are regenerated.

### 3. XRD Assignment

- Select one or more systems.
- Mark the samples for which XRD data is available. Marked samples appear in
  **bold** in `phase_table_<System>_<temp>.xlsx`.
- The tool reports coverage and recommends phases that still lack XRD
  confirmation.

---

## Output structure

```
<base_path>/
  <System>/
    phases_<System>.txt                    # theoretical phase list for the system
    <temp>/
      SEM_results_<System>_<temp>.xlsx     # per-sample measured compositions
      phase_table_<System>_<temp>.xlsx     # cluster → phase association table
      <System>_<temp>.exp                  # measured compositions for plotting
      <System>_<temp>_phase_predic.exp     # predicted (substituted) compositions
      clustering_history.json              # stored clustering results
      diagrams/
        <sample>_ternary_final.png         # saved ternary diagram (300 DPI)
      reports/
        <temp>_<sample>/                   # sample-specific reports
          <System>_<temp>_<sample>.docx
```

---

## Configuration (`config.json`)

```json
{
  "normalization": {
    "enabled": true,
    "apply_to_both_types": true
  },
  "images": {
    "embed_images": true,
    "min_width_columns": 4,
    "max_width_columns": 8,
    "preserve_aspect_ratio": true
  }
}
```

- `normalization.enabled` – turn composition normalisation on/off.
- `normalization.apply_to_both_types` – apply to both INCA and AZTEC reports
  (if `false`, only INCA).
- `images.embed_images` – extract and embed SEM images from **AZTEC** reports.
- `min_width_columns` / `max_width_columns` – display width bounds (in Excel
  columns) for embedded images.
- `preserve_aspect_ratio` – keep the original image proportions.

Additional tuning values (clustering epsilon, plot DPI, phase distance
threshold, history length, etc.) live in `constants.py`.

---

## Phase management

Two phase sources are used:

- **`phases_<System>.txt`** – the phase list for a single system. Created and
  edited through the GUI.
- **`master_phases.json`** – a local database mapping each element to all phases
  that contain it. When a system is processed, relevant phases are pulled from the
  master file and merged into the system phase list.

`master_phases.json` is **machine-specific** and is **not committed** to the
repository (see `.gitignore`). A starter file is provided:

```bash
cp master_phases_template.json master_phases.json
```

If `master_phases.json` is missing, the program builds it automatically by
scanning existing `phases_*.txt` files.

---

## Project structure

| File | Responsibility |
|------|----------------|
| `main.py` | Entry point and start menu. |
| `reports.py` | Report grouping, the full New Analysis pipeline, phase association. |
| `tables.py` | `.docx` table extraction, normalisation, weight→atomic, image embedding. |
| `structure.py` | Output folder/file structure creation. |
| `to_exp.py` | `.exp` file generation, phase-prediction `.exp`, phase table `.xlsx`. |
| `clustering.py` | DBSCAN clustering, silhouette scoring, ternary plotting. |
| `clustering_history.py` | Persisting and loading clustering history. |
| `phases.py` | Chemical formula parsing and composition calculation (incl. ranges). |
| `phase_manager.py` | System phase files and master phase database management. |
| `phase_reassociation.py` | Phase Reassociation workflow. |
| `xrd_assignment.py` | XRD Assignment workflow. |
| `tkinter_clustering.py` | Interactive clustering / phase-selection GUI. |
| `tkinter_selection.py`, `matplotlib_selection.py` | Image selection interfaces. |
| `input_list_test.py` | Reusable validated list-builder GUI. |
| `constants.py` | Centralised configuration constants. |
| `elements.py` | Element database loader. |
| `logging_config.py` | Centralised, colourised logging. |

---

## Troubleshooting

- **No ternary diagrams saved** – make sure the `diagrams/` folder exists; it is
  created automatically during processing.
- **"Spectrum Unknown" labels** – the `.docx` format was not recognised; verify it
  is a valid INCA or AZTEC report.
- **No `.exp` file created** – check the log output; the Excel file may lack valid
  data.
- **"Student coefficient file not found"** – the default value is used, which is
  fine for large samples.
- **Clustering is slow** – lower `DEFAULT_EPS_STEPS` in `constants.py`.
- **Phase GUI does not appear** – the phase file may already exist; check
  `<System>/phases_<System>.txt`.

All steps are written to the console with timestamped, colourised log messages.

---

## Current work in progress

- **Reassosiation** - is not consistent and does not work as intended yet.
- **Saving Diagrams** - current version does not save the diagrams properly and the format is not of the desired shape
