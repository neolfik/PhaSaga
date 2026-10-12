# Quick Start

> **AI assistance note:** AI tooling was used during development to speed things
> up and to make the scripts more efficient and faster.

A condensed guide to running the Phase Association Analysis tool. See
[`README.md`](README.md) for full documentation.

## 1. Install

```bash
pip install numpy pandas openpyxl scikit-learn matplotlib Pillow docx2python termcolor
```

On Linux you may also need Tkinter:

```bash
sudo apt install python3-tk
```

## 2. Prepare inputs

- Put the SEM reports in one folder.
- Name each report `<System>_<temp>_<sample>.docx`, e.g. `InLaNi_500_1a.docx`.
  - The letter `a` is the overall composition; `b`, `c`, … are measurements.
- Make sure `elements.csv`, `student.csv` and `config.json` are present next to
  the scripts.
- First run only: copy the phase template.

```bash
cp master_phases_template.json master_phases.json
```

## 3. Run

```bash
python main.py
```

### New Analysis

1. **Select Folder…** → pick the folder with the `.docx` reports.
2. Enter the theoretical phases for each new system in the phase-list window
   (validated against the system elements).
3. For each sample, pick the clustering (2 / 3 clusters or a custom lasso
   selection) and associate each cluster with a phase.

### Phase Reassociation

Select an already processed system/temperature to edit its phase list and
cluster→phase associations without re-reading the raw reports.

### XRD Assignment

Select systems and mark the samples that have XRD data; marked samples become
**bold** in the phase table, and the tool recommends phases still awaiting XRD
confirmation.

## 4. Output

```
<System>/<temp>/
  SEM_results_<System>_<temp>.xlsx
  phase_table_<System>_<temp>.xlsx
  <System>_<temp>.exp
  <System>_<temp>_phase_predic.exp
  clustering_history.json
  diagrams/<sample>_ternary_final.png
  reports/<temp>_<sample>/<System>_<temp>_<sample>.docx
```

## 5. Tuning

Edit `config.json` for normalisation and image options, and `constants.py` for
clustering/plotting parameters.

| Setting | File | Effect |
|---------|------|--------|
| `normalization.enabled` | `config.json` | Enable/disable composition normalisation |
| `images.embed_images` | `config.json` | Embed SEM images from AZTEC reports |
| `DEFAULT_EPS_STEPS` | `constants.py` | Lower to speed up clustering |
| `PLOT_DPI` | `constants.py` | Resolution of saved ternary diagrams |
| `MAX_HISTORICAL_SAMPLES` | `constants.py` | Number of past samples shown in plots |
| `PHASE_DISTANCE_THRESHOLD` | `constants.py` | Phase-candidate matching tolerance |

## Troubleshooting

| Problem | Solution |
|---------|----------|
| No ternary diagrams | The `diagrams/` folder is created automatically; check the log |
| "Spectrum Unknown" | Report is not a recognised INCA/AZTEC file |
| No `.exp` created | Check the log; the Excel file may lack valid data |
| "Student coefficient file not found" | Default value is used — fine for large samples |
| Clustering too slow | Lower `DEFAULT_EPS_STEPS` in `constants.py` |
| Phase GUI missing | A phase file already exists: `<System>/phases_<System>.txt` |
