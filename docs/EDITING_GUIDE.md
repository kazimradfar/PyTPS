# PyTPS editing guide

How to change PyTPS yourself: add something, remove something, or change how it looks or works. It is written for
someone who knows radiotherapy physics and a little Python, not for a professional programmer. Every recipe names
the exact file and the place inside it.

Contents

1. Tools you need (once)
2. Get the code and run it
3. The working cycle of every change
4. Where is what (map of the code)
5. Recipes: texts, menus, buttons, panels
6. Recipes: physics and planning
7. Recipes: documents, version, release
8. Tests
9. Asking an AI assistant or a programmer for help
10. When something goes wrong
11. Rules of the project

---

## 1. Tools you need (once)

| Tool | Why | Where |
|---|---|---|
| Python 3.10 or newer (3.12 recommended) | runs PyTPS | python.org; on Windows tick *Add python.exe to PATH* |
| Git | downloads the code and keeps the history of every change | git-scm.com |
| VS Code (or any editor) | edits the files | code.visualstudio.com, with the *Python* extension |
| GitHub account with write access to the repository | to publish changes | github.com |

## 2. Get the code and run it

```
git clone https://github.com/kazimradfar/PyTPS.git
cd PyTPS
python -m venv .venv
.venv\Scripts\activate            (Linux/macOS: source .venv/bin/activate)
python -m pip install -r requirements.txt pytest
python run_pytps.py
```

On Windows `start_pytps.bat` does the same steps automatically. Open the `PyTPS` folder in VS Code
(*File ▸ Open Folder*); choose the interpreter in `.venv` when VS Code asks.

Useful start options while you test a change (all options: `python run_pytps.py --help`):

```
python run_pytps.py --phantom "Pelvis (prostate)" --demo-plan 0,90,180,270           # plan ready at once
python run_pytps.py --phantom "Thorax (lung tumour)" --demo-plan 0 --arc --optimise 40
python run_pytps.py --guide-tbi
```

## 3. The working cycle of every change

1. **Update** your copy: `git pull`
2. **Find** the place: use the map in chapter 4, or search all files in VS Code with Ctrl + Shift + F
   (for example search the text of a button you see in the program).
3. **Change** the file and save it.
4. **Run** the program and try the change: `python run_pytps.py …`
5. **Test**: `python -m pytest tests -q` must end with *passed* and no *failed* (about one minute).
6. **Commit** (a small change with a clear message):
   ```
   git add -A
   git commit -m "Evaluation: add D1cc to the statistics"
   ```
7. **Push**: `git push`. On GitHub, the *Actions* tab runs the tests again on a clean computer and makes
   screenshots (branch `ci-shots`). A green tick means everything passed.
8. **Build** the Windows program when a version is ready (chapter 7.4).

If a change goes wrong before the commit: `git checkout -- <file>` restores the file; `git stash` puts all changes
aside. After a commit: `git revert <commit>` creates a new commit that undoes it. The history is never lost.

## 4. Where is what (map of the code)

The program has two layers. `pytps/core/` is the physics and data (no windows); `pytps/gui/` is the user interface.

| You want to change … | File | Look for |
|---|---|---|
| version number | `pytps/__init__.py` and `installer/pytps.iss` | `__version__`, `AppVersion` |
| text of Help ▸ About, author, licence line | `pytps/gui/main_window.py` | `def about` |
| menus (File, Edit, View, …) | `pytps/gui/main_window.py` | `def _build_actions`, lines `mb.addMenu(…)` |
| toolbar buttons | `pytps/gui/main_window.py` | `tb.addAction`, `tb.addWidget` in `_build_actions` |
| keyboard shortcuts | `pytps/gui/main_window.py` | `shortcut="…"` |
| window title | `pytps/gui/main_window.py` | `setWindowTitle` |
| workspaces (Patient, Contouring, Planning, Evaluation) and lower tabs | `pytps/gui/main_window.py` | `self.work.addTab`, `self.lower.addTab` |
| colours and style of the panels | `pytps/gui/theme.py` | `apply_theme` |
| icons of the toolbar | `pytps/gui/icons.py` | one small drawing function per icon |
| program icon | `pytps/resources/pytps.ico` (Windows) and `pytps.png` | replace the files, same names |
| Patient workspace: DICOM import, phantom list, CT-to-density table | `pytps/gui/panels.py` | `class PatientPanel` |
| Contouring workspace: structure table, margin, Boolean, threshold | `pytps/gui/panels.py` | `class ContourPanel` |
| structure types (PTV, ORGAN, …) | `pytps/core/structures.py` | `STRUCT_TYPES` |
| contour operations (margin, Boolean, interpolation) | `pytps/core/structures.py` | `class StructureSet` |
| practice phantoms | `pytps/core/phantoms.py` | one function per phantom, list `PHANTOMS` |
| slice views, mouse tools, drawing, dragging fields | `pytps/gui/sliceview.py` | `class SliceView` |
| isodose levels and colours, colour bar, field outlines | `pytps/gui/overlays.py` | `ISODOSE`, `class DoseOverlay`, `class BeamOverlay` |
| window/level presets | `pytps/gui/state.py` | `WL_PRESETS` |
| BEV, 3D and room views | `pytps/gui/beamviews.py` | `BEVView`, `Model3DView`, `RoomView` |
| beam table, isocentre, wedges, MLC options | `pytps/gui/planning.py` | `class BeamsPanel`, `COLS` |
| prescription, normalisation, dose grid | `pytps/gui/planning.py` | `class PrescriptionPanel` |
| beam geometry (gantry, collimator, couch, MLC leaves, SAD) | `pytps/core/beams.py` | `SAD`, `LEAF_EDGES`, `class Beam`, `class Frame` |
| beam data (PDD, output factors, energies) | `pytps/core/beamdata.py` | `default_models` |
| beam data window (Tools menu) | `pytps/gui/beamdata_dialog.py` | `class BeamDataDialog` |
| dose calculation | `pytps/core/dose_pb.py` | `class DoseEngine` |
| MU, normalisation, DVH, plan sum | `pytps/core/plan.py` | `calculate`, `normalise`, `dvh`, `plan_sum` |
| cost functions and optimiser | `pytps/core/optimise.py` | `COST_TYPES`, `COST_HELP`, `evaluate_costs`, `class Optimiser`, `default_costs` |
| IMRT Constraints and Optimisation tabs | `pytps/gui/optim_panels.py` | `ConstraintsPanel`, `OptimisationPanel` |
| statistics, goals, point doses, PDF report, DVH and profile plots | `pytps/gui/evaluation.py` | `EvaluationPanel` (`COLS`, `rows`), `draw_dvh`, `ProfileWidget`, `write_report` |
| DICOM import/export | `pytps/core/dicomio.py` | `load_ct`, `load_rtstruct`, `save_rtplan`, `load_rtplan`, `save_rtdose`, … |
| guided exercise VMAT-TBI | `pytps/gui/guide.py` | `STEPS`, `THESIS_ISO`, the `step…` and `check…` functions |
| user manual (text and viewer) | `docs/USER_MANUAL.md`, `pytps/gui/manual.py` | |
| command-line options | `pytps/__main__.py` | `ap.add_argument` |
| tests | `tests/test_core.py`, `test_dose.py`, `test_dicom.py`, `test_gui.py` | |
| automatic build and release | `.github/workflows/build.yml`, `installer/pytps.iss` | |

`AppState` in `pytps/gui/state.py` holds everything that is open: `state.image`, `state.ss` (structures),
`state.plans`, `state.plan` (current plan), `state.compare`, `state.engine` (dose engine), `state.models` (beam data).
When something changes, code calls `state.changed.emit("plan")` (or `"image"`, `"structures"`, `"dose"`, `"beam"` …)
and all views and panels update themselves. `state.message.emit("text")` writes to the status bar and the
Messages tab.

## 5. Recipes: texts, menus, buttons, panels

### 5.1 Change a text, label or tooltip

Search the visible text (Ctrl + Shift + F in VS Code), change it between the quotes, save, run.
Example: in `pytps/gui/planning.py` the button `"Add arc"` can become `"Add VMAT arc"`.
If a test fails afterwards, the test probably looks for the old text: change it there too.

### 5.2 Change the About window

`pytps/gui/main_window.py`, function `about`. The text is HTML: `<b>bold</b>`, `<br>` new line,
`<a href='https://…'>link</a>`. Example: add the university after the author line:

```python
f"Developed by <b>Kazim Radfar</b>, PhD student in Medical Physics.<br>"
f"Tehran University of Medical Sciences<br><br>"
```

### 5.3 Add a menu item

In `_build_actions` (`pytps/gui/main_window.py`) each menu is built like this:

```python
m = mb.addMenu("&Tools")
m.addAction(self._act("Measure distance", lambda: self.set_tool("ruler"), icons.ruler()))
m.addAction(self._act("Beam data and model…", self.beam_data))
```

`self._act(text, function, icon=None, shortcut=None, tip=None, checkable=False)` makes the item. To add one:

```python
m.addAction(self._act("Show plan summary…", self.plan_summary, shortcut="Ctrl+I", tip="MU and beams of the plan"))
```

and add the function to the `MainWindow` class (next to the other functions such as `def about`):

```python
def plan_summary(self):
    pl = self.state.plan
    if pl is None:
        return
    text = "\n".join(f"{b.name}: gantry {b.gantry:.0f}°, {b.mu:.0f} MU" for b in pl.beams)
    QMessageBox.information(self, "Plan summary", text or "No beams")
```

### 5.4 Remove a menu item, button or feature

Do not delete large blocks at once. First remove only the line that shows it, for example the line
`m.addAction(self._act("Plan sum…", …))`. Run the program and the tests. The function behind it can stay; it does no
harm. If a test uses the removed item, delete that test or the part of it, and say so in the commit message.
To remove a whole workspace tab, remove its `self.work.addTab(…)` line in `main_window.py`.

### 5.5 Add a toolbar button

In `_build_actions`, after the menus, the toolbar is filled with `tb.addAction(…)`. Reuse a menu action
(so the menu and the button do the same thing):

```python
a = self._act("Plan summary", self.plan_summary, icons.calc())
tb.addAction(a)
```

New icons are drawn in `pytps/gui/icons.py`; copy a small function such as `camera()` and change the drawing.
Do not use logos or icons of commercial planning systems.

### 5.6 Add a button to a panel

Panels are built in their `__init__` with layouts. Example from the Evaluation panel (`pytps/gui/evaluation.py`):

```python
b = QPushButton("PDF report…"); b.clicked.connect(self.report); r3.addWidget(b)
```

Add a line like it, and a function `def …(self):` in the same class.

### 5.7 Change colours

- Panels, tabs, toolbar: `pytps/gui/theme.py` (RGB values and the style sheet).
- Isodose levels and their colours: `ISODOSE` in `pytps/gui/overlays.py`, pairs of (per cent, (R, G, B)).
  Example to add a 110 % line: `(110, (255, 0, 255)),` as the first entry. The colour bar follows automatically.
- Default colours of new structures: `PALETTE` in `pytps/core/structures.py`.
- Background of the slice views: `pytps/gui/sliceview.py` (search `fillRect(self.rect()`).

### 5.8 Add a window/level preset

`WL_PRESETS` in `pytps/gui/state.py`: `"Name": (level, window)`, for example `"Liver": (60, 160),`.

### 5.9 Add a structure type

Add the name to `STRUCT_TYPES` in `pytps/core/structures.py`. If the type should be treated as a target by the
default cost functions, see `default_costs` in `pytps/core/optimise.py`.

## 6. Recipes: physics and planning

### 6.1 Add a practice phantom

In `pytps/core/phantoms.py` write a function like `water_box` (coordinates in mm, HU values in the dictionary `HU`):

```python
def cylinder(sp=(2.5, 2.5, 3.0)):
    x, y, z = _grid((-180, 180), (-180, 180), (-120, 120), sp)
    B = _Builder(x, y, z, "CYLINDER", "Water cylinder 30 cm with a 4 cm target")
    body = _ell(B.X, B.Y, 0, 0, 150, 150)
    for k, zz in enumerate(z):
        B.ct[k][body] = 0
        B.mask("BODY", k, body, (127, 220, 127), "EXTERNAL")
        if abs(zz) <= 20:
            ptv = _ell(B.X, B.Y, 0, 0, 20, 20)
            B.mask("PTV", k, ptv, (255, 60, 60), "PTV")
    return B.image(sp)
```

and register it in `PHANTOMS` at the end of the file: `"Water cylinder 30 cm": cylinder,`.
It then appears in the phantom list and can be started with `--phantom "Water cylinder 30 cm"`.

### 6.2 Change beam data or add an energy

`default_models` in `pytps/core/beamdata.py` returns `{"6X": …, "10X": …}`. Each `BeamModel` has PDD tables, output
factors, head scatter, wedge factors and the calibration; the model parameters are fitted to them (`fit`).
To add 15 MV, copy the `m10` block, change the name to `"15X"` and its data, and add it to the returned dictionary.
The energy list of the beam table is taken from this dictionary automatically.
Students can also change the data in the program (Tools ▸ Beam data and model); that change is not saved in the code.

### 6.3 Add a cost function

All in `pytps/core/optimise.py`:

1. add the name to `COST_TYPES`;
2. add the labels of its two parameters to `COST_HELP`;
3. in `evaluate_costs` add a branch `elif t == "My cost":` that computes the cost `f` and its derivative `gd` for each
   voxel dose `d` (copy the *Maximum Dose* branch as a start: it is the simplest) and sets `c.achieved`;
4. optionally use it in `default_costs`.

The IMRT Constraints table shows the new type automatically. Add a test that optimises with it (chapter 8).

### 6.4 Change the default cost functions

`default_costs` in `pytps/core/optimise.py`: rules per structure name (cord, brainstem, rectum → Serial; mandible,
femoral heads → Maximum Dose; others → Parallel) and the target cost functions. Change doses, weights or rules there.

### 6.5 Change the optimiser settings shown to the user

Defaults: `class OptSettings` in `pytps/core/optimise.py`. The fields of the Optimisation tab:
`OptimisationPanel` in `pytps/gui/optim_panels.py`.

### 6.6 Add a column to the dose statistics

`pytps/gui/evaluation.py`, class `EvaluationPanel`: add the header to `COLS` and the value to the list in `rows`,
in the same position. Example D1cc needs the volume: `d["D"](100 * 1.0 / d["cc"])` (dose to 1 cc).

### 6.7 Add a clinical-goal metric

`pytps/gui/evaluation.py`: the list in `add_goal` (`["Dmean", "Dmax", …]`), the calculation in `goal_value` and the
label in the goal table (`txt = {…}`).

### 6.8 Change the guided exercise

`pytps/gui/guide.py`: `STEPS` holds the title and text of each step (HTML) and the functions behind **Show me** and
**Check**. The isocentres of the TBI plan are in `THESIS_ISO`; the prescription, cost functions and goals are written in
the step functions. A new exercise can be made by copying `guide.py` to a new file, changing it, and adding a menu
item that opens it (see `show_guide` in `main_window.py`).

### 6.9 Change the dose engine

`pytps/core/dose_pb.py`. Every change here changes all doses: run `tests/test_dose.py` (calibration 1 cGy/MU at dmax,
PDD, direction of the gantry, lung) and compare a few point doses before and after. Write in the commit message what
changed physically.

## 7. Recipes: documents, version, release

### 7.1 Edit the user manual

`docs/USER_MANUAL.md` (Markdown: `#` headings, `**bold**`, `| tables |`, `![caption](images/file.png)`).
Every `## ` heading becomes an entry in the chapter list of Help ▸ User manual. Images go into `docs/images/`.
GitHub shows the file nicely formatted; check it there after the push.

### 7.2 New screenshots for the manual

Each push makes fresh screenshots (Actions, branch `ci-shots`). Download them from the branch `ci-shots` on GitHub,
or make one locally:
`python run_pytps.py --phantom "Pelvis (prostate)" --demo-plan 0,90,180,270 --size 1600x900 --screenshot docs/images/x.png`.
Only phantoms or de-identified images with permission, never patient data.

### 7.3 New version number

Change it in both `pytps/__init__.py` (`__version__ = "0.2.3"`) and `installer/pytps.iss`
(`#define AppVersion "0.2.3"`), add a line to `ROADMAP.md`, commit and push.

### 7.4 Build the Windows program and publish a release

On GitHub: *Actions* ▸ *PyTPS* ▸ *Run workflow* ▸ branch `main`, keep *Build the Windows program* ticked ▸ *Run*.
After about 15 minutes the release `v<version>` appears under *Releases* with the setup program and a portable zip.
The build is tested before it is published (self-test, silent install, uninstall). Building the same version again
replaces that release.

To build locally on Windows instead:

```
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --clean --windowed --name PyTPS --icon pytps/resources/pytps.ico ^
  --add-data "pytps/resources;pytps/resources" --add-data "docs;docs" ^
  --add-data "LICENSE;." --add-data "THIRD_PARTY_LICENSES.md;." ^
  --collect-submodules pydicom --collect-submodules skimage.measure run_pytps.py
dist\PyTPS\PyTPS.exe --self-test result.json
```

and the setup program with Inno Setup 6: `ISCC.exe /DAppVersion=0.2.3 installer\pytps.iss`.

### 7.5 Rename the program

Search `PyTPS` in all files (Ctrl + Shift + F) and replace it in the texts, `installer/pytps.iss` (keep its `AppId`
so updates replace the old installation), the workflow (`--name PyTPS`) and the documents. The Python package
folder `pytps` can keep its name.

## 8. Tests

Tests are small Python functions in `tests/` whose names start with `test_`. They run with
`python -m pytest tests -q` (a single file: `python -m pytest tests/test_dose.py -q`; a single test:
`… -k name`). The GUI tests open the real windows without showing them.

Every fixed bug and every new feature should get a test, if possible against a known value. Example:

```python
def test_d1cc_column():
    from PySide6.QtWidgets import QApplication
    from pytps.gui.main_window import MainWindow
    from pytps.gui.planning import demo_beams
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    w.patient.load_phantom("Pelvis (prostate)")
    demo_beams(w.state, [0, 90, 180, 270]); w.rx_panel.refresh(); w.rx_panel.calculate()
    rows = w.evaluation.rows()
    ptv = next(r for r in rows if r[0] == "PTV")
    rx = w.state.plan.rx.dose
    assert 0.9 * rx < ptv[3] < 1.1 * rx        # mean dose near the prescription
```

## 9. Asking an AI assistant or a programmer for help

Give them the repository link and a precise request. A good request names what you see now, what you want, where
it is (use the map in chapter 4) and how to check it. Template:

```
Repository: https://github.com/kazimradfar/PyTPS (Python, PySide6). Read README.md and docs/EDITING_GUIDE.md first.
Change: <what to add / remove / change, in one or two sentences>.
Where: <file and function from the map, if known>.
Now: <what the program does now>. Wanted: <what it should do>.
Check: run "python -m pytest tests -q" (all must pass) and "python run_pytps.py --phantom ... --demo-plan ...";
add a test for the change; update docs/USER_MANUAL.md if the user sees the change; small commits; MIT licence;
no patient data; no vendor names, logos or look-alike designs.
```

Paste error messages completely (the last lines of the red text are the most important).

## 10. When something goes wrong

| Message or problem | Cause and solution |
|---|---|
| `No module named 'PySide6'` (or numpy, pydicom …) | the environment is not active or not installed: `.venv\Scripts\activate`, then `python -m pip install -r requirements.txt` |
| `can't open file 'run_pytps.py'` | you are not in the PyTPS folder: `cd PyTPS` |
| `IndentationError` / `SyntaxError` with a line number | Python needs the same indentation (4 spaces) inside a block, and closed brackets and quotes; look at the given line and the line above |
| `NameError: name 'x' is not defined` | a missing import at the top of the file or a typing error in a name |
| `AttributeError: … has no attribute …` | the name of a function or field is different; search for it in the file |
| the program starts but the change is not visible | wrong file or a second copy of PyTPS; check the folder with `python -c "import pytps; print(pytps.__file__)"` |
| a test fails | read the line with `assert`; either the change broke something, or the test checks the old behaviour and must be updated |
| red cross in GitHub Actions | open the run, click the red step, read the last lines; the same command can be run locally |
| `git push` rejected | someone else pushed first: `git pull`, then `git push` |
| `git pull` reports a conflict | the same lines were changed in two places: open the file, keep the right version between the `<<<<<<<` and `>>>>>>>` marks, then `git add` and `git commit` |
| `cannot lock ref` during `git fetch` | two fetches at once (for example VS Code): run the command again |

## 11. Rules of the project

- **No patient data** in the repository, in screenshots or in test files; use the phantoms. Real data stay on the
  local computer and de-identified.
- **Own design**: the workflow may follow common planning systems, but no vendor names, logos, icons or copied
  screens.
- **MIT licence**: keep the `LICENSE` file and the copyright notice; contributions are under the same licence.
- **Tests pass before a push**, one topic per commit, clear commit messages in English.
- The manual and this guide are updated when a command, a menu or a behaviour changes.
