# PyTPS — radiotherapy treatment planning system for teaching

PyTPS is a desktop program for **teaching treatment planning** to medical physics students (MSc level).
It follows the workflow of a modern planning system: patient import, contouring, beams, prescription,
dose calculation and plan evaluation. It has its own design and is not affiliated with any vendor.

Developed by **Kazim Radfar**, PhD student in Medical Physics.

- **Download for Windows:** [latest release](https://github.com/kazimradfar/PyTPS/releases/latest) (setup program or portable zip)
- **User manual:** [docs/USER_MANUAL.md](docs/USER_MANUAL.md) (also in the program: Help ▸ User manual, Shift + F1)


> **Not for clinical use.** PyTPS is not a medical device, is not commissioned for any treatment machine
> and must not be used to plan, check or deliver patient treatments. The beam data are generic teaching values.

## Features (version 0.2.2)

- **Patient**: import DICOM CT, RT Structure Set (read locally; names and IDs are replaced by an anonymous
  code), practice phantoms (water, thorax, pelvis, head and neck, breast, whole body for TBI),
  editable CT-to-electron-density table.
- **Viewer**: linked transverse, coronal and sagittal views, 2 × 2 / one large + three / single layouts; any view,
  including the beam's-eye view, the 3D model and the room view, can be the single or large view;
  window/level presets and mouse window/level, zoom, pan, measuring.
- **Contouring**: brush, eraser, polygon (add or subtract), 3D margins (different head-foot margin),
  Boolean operations, threshold, interpolation between slices, fill holes, keep largest part,
  body outline from CT, structure types, colours and density overrides, undo / redo,
  export as RT Structure Set.
- **Beams** (added and edited by hand): static fields and arcs, isocentre (typed, at the crosshair or the
  target centre), gantry, collimator, couch, jaws, energy (6 and 10 MV), MLC (open, conformal to a structure
  with margin, manual leaf editing in the beam's eye view), wedges, opposed beams, copy, weights,
  patient position (HFS, FFS, HFP, FFP), source–skin distance.
- **Beam display**: divergent field outlines in all slices, central axis, arc control points,
  beam's eye view with digitally reconstructed radiograph (DRR), projected structures, jaws and MLC
  (drag the jaws and leaves), and a 3D model of patient and beams.
- **Dose**: pencil-beam calculation (fluence convolution with penumbra and scatter kernels, radiological
  depth through the density volume), MU calculation and normalisation (isocentre, mean, D95, D50,
  prescription isodose), isodose lines or colour wash with a colour bar / isodose legend in Gy and %.
- **IMRT constraints**: cost functions per structure (target penalty, target EUD, quadratic under/overdose,
  under/overdose DVH, maximum dose, serial, parallel, conformality), as objective or constraint, with weights,
  layering and a default set to start from; achieved values are shown after optimisation.
- **Optimisation**: Stage 1 fluence optimisation for static IMRT beams and VMAT arcs, Stage 2 MLC segmentation
  (intensity levels for step-and-shoot, apertures per arc sector for VMAT) with segment-weight optimisation,
  MU and delivery-time estimate, cost history. Beams that are not optimised count as a bias dose.
- **Plans**: several plans per patient (new, copy, rename, delete), plan sum, comparison (dashed DVH and
  statistics side by side), dose-difference display.
- **Evaluation**: DVH, dose statistics per structure (min, mean, max, D98, D95, D50, D2, V95%), clinical goals with
  pass/fail, point doses, beam MU and SSD, dose profile along a line, PDF plan report.
- **Export**: main view or whole window as image, DVH and dose profile as high-resolution images (white background,
  for reports) and as CSV data, dose statistics as CSV.
- **DICOM RT**: export and import of RT Plan (jaws, MLC control points, MU, wedges) and RT Dose; an imported
  dose can be compared with the PyTPS dose.
- **Beam data editor** (Tools menu): PDD, output factors, head scatter, wedge factors, calibration; refit the
  model and see data and model together.
- **Beam data**: generic 6 MV and 10 MV data (PDD for several field sizes, output factors, head scatter,
  wedge factors); the model parameters are fitted to the data, as in commissioning.

Planned next: see `ROADMAP.md`.

## Run from source

Easiest on Windows: download the code (green *Code* button ▸ *Download ZIP*, or `git clone
https://github.com/kazimradfar/PyTPS.git`) and double-click **`start_pytps.bat`**. The first start creates a private
Python environment (`.venv`) in the folder and installs all dependencies (internet needed once). On Linux or macOS:
`./start_pytps.sh`. Python 3.10 or newer must be installed.

By hand:

```
python -m pip install -r requirements.txt
python run_pytps.py                       # or: python -m pytps
python run_pytps.py --phantom "Thorax (lung tumour)" --demo-plan 0,90,180,270
python run_pytps.py --phantom "Pelvis (prostate)" --demo-plan 0,52,104,156,204,256,308 --optimise 80
python run_pytps.py --phantom "Head and neck" --demo-plan 0 --arc --optimise 60
```

### First inverse plan (example)
1. Patient: load a phantom or import CT + structures. 2. Planning ▸ Beams: add beams or an arc, set
**MLC = optimised**, isocentre at the target centre. 3. Prescription: dose, fractions, target, normalisation.
4. IMRT Constraints: start from *Defaults* and adjust. 5. Optimisation: *Optimise (1 + 2)*.
6. Evaluation: DVH, goals, compare with a copy of the plan, PDF report.

Python 3.10 or newer. Tested on Windows and Linux. A 4 mm dose grid needs about 1–2 GB of memory for a pelvis or thorax CT.

## Windows program

The Windows setup program and a portable zip are built by GitHub Actions **on request only**:
Actions ▸ *PyTPS* ▸ *Run workflow* ▸ branch `main`, tick *Build the Windows program*. The build is tested
(self-test, silent install, uninstall) and published as the release `v<version>`.
Pushes only run the tests and the screenshots (branch `ci-shots`).

## Dependencies

| Package | Used for |
|---|---|
| PySide6 (Qt 6) | the user interface |
| numpy, scipy | arrays, dose calculation, convolution, optimisation |
| scikit-image | contours of structures |
| pydicom | reading and writing DICOM (CT, RT Structure Set, RT Plan, RT Dose) |
| pytest, PyInstaller | tests and the Windows build (developers only) |

All are listed in `requirements.txt` and `pyproject.toml` (`pip install .` installs PyTPS as a package with the
command `pytps`). The Windows program contains Python and all packages, so nothing else needs to be installed.

## Repository layout

| Path | Contents |
|---|---|
| `pytps/core/` | images, structures, phantoms, DICOM, beams, beam data, dose engine, plans, optimiser (no user interface) |
| `pytps/gui/` | main window, panels, views, overlays, evaluation, guided exercise, manual viewer, icons |
| `pytps/resources/` | program icon |
| `tests/` | automatic tests (`python -m pytest tests -q`) |
| `docs/` | user manual with images, editing guide |
| `installer/` | Inno Setup script of the Windows setup program |
| `.github/workflows/build.yml` | tests, screenshots and (on request) the Windows build and release |
| `run_pytps.py`, `start_pytps.bat`, `start_pytps.sh` | start scripts |

## Mouse and keys

| Action | How |
|---|---|
| Move the crosshair | left click (crosshair tool) |
| Change slice | mouse wheel, ↑ / ↓, Page Up / Page Down (Shift + wheel = 5 slices) |
| Zoom / pan | Ctrl + wheel / middle button drag |
| Window / level | right button drag, or the presets |
| Brush size | spin box in the toolbar |
| Polygon | click points, double-click or right-click to close; Shift = subtract |
| Resize a field / move the isocentre | drag a field edge / the red isocentre cross in a slice view |
| Rotate the gantry | drag the round gantry handle in the transverse view (Shift: 5° steps), or turn the Gantry dial in the Beams tab |
| Undo / redo | Ctrl + Z / Ctrl + Y |
| Calculate dose | F5 |
| Optimise (Stage 1 + 2) | F6 |

## Coordinate conventions

Patient coordinates are DICOM (LPS, mm): +x patient left, +y posterior, +z head. For a head-first
supine patient, gantry 0° is an anterior beam and gantry 90° enters from the patient's left.
Field coordinates X and Y are at the isocentre plane; MLC leaves move along X.

## Citation

If you use PyTPS in teaching or research, please cite it. GitHub's **Cite this repository** button (right side of
the repository page) gives the reference in APA and BibTeX from `CITATION.cff`.

## Licence

MIT, see `LICENSE`. The Windows program also contains third-party software under its own licences, listed in
`THIRD_PARTY_LICENSES.md`. Data you import stay on your computer; please use de-identified data and follow the rules
of your institution.
