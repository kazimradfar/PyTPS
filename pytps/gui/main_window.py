"""Main window: menu bar, toolbar, workspace panels, linked image views and the lower information area."""
from __future__ import annotations

import os

import numpy as np
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QColor, QKeySequence, QPainter
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFileDialog, QFrame, QGridLayout, QLabel, QMainWindow, QMessageBox,
                               QPlainTextEdit, QScrollArea, QSpinBox, QSplitter, QTabWidget, QToolBar, QVBoxLayout, QWidget)

from .. import DISCLAIMER, __version__
from ..core.phantoms import PHANTOMS
from . import icons
from .beamviews import BeamViews
from .evaluation import DVHWidget, EvaluationPanel, ProfileWidget
from .overlays import BeamOverlay, DoseOverlay, PointOverlay
from .panels import ContourPanel, PatientPanel
from .optim_panels import ConstraintsPanel, OptimisationPanel
from .planning import BeamsPanel, PrescriptionPanel
from .sliceview import SliceView
from .state import WL_PRESETS, AppState


SOURCE_URL = "https://github.com/kazimradfar/PyTPS"


class Placeholder(QWidget):
    """Fourth view until beams exist (beam's-eye view / 3D)."""

    def __init__(self, title, text, parent=None):
        super().__init__(parent)
        self.title, self.text = title, text
        self.setMinimumSize(160, 140)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0))
        p.setPen(QColor(232, 238, 245)); f = p.font(); f.setBold(True); p.setFont(f); p.drawText(8, 16, self.title)
        f.setBold(False); p.setFont(f); p.setPen(QColor(140, 152, 168))
        p.drawText(self.rect().adjusted(20, 20, -20, -20), Qt.AlignCenter | Qt.TextWordWrap, self.text)
        p.end()


VIEW_NAMES = ["Transverse", "Coronal", "Sagittal", "BEV", "3D", "Room"]


class ViewGrid(QWidget):
    """Image views in 2 x 2, single, or one large + three small layouts. The focused view is enlarged.

    The fourth view holds the beam's eye view, the 3D model and the room view as tabs; any of them can be the
    single or large view (View ▸ Main view, the toolbar list, or a click into the view)."""

    def __init__(self, views, parent=None):
        super().__init__(parent)
        self.views = views
        self.focus = views[0]
        self.mode = "4"
        self.on_focus = []             # callbacks(name) when the main view changes
        self.grid = QGridLayout(self); self.grid.setContentsMargins(2, 2, 2, 2); self.grid.setSpacing(3)
        for v in views:
            if isinstance(v, SliceView):
                v.activated.connect(self.set_focus)
        bv = views[3]
        if isinstance(bv, QTabWidget):
            for w in [bv.widget(i) for i in range(bv.count())] + [bv.tabBar()]:
                w.installEventFilter(self)
            bv.currentChanged.connect(lambda _i: self._notify() if self.focus is bv else None)
        self.apply()

    def eventFilter(self, obj, ev):
        from PySide6.QtCore import QEvent
        if ev.type() == QEvent.MouseButtonPress:
            self.set_focus(self.views[3])
        return False

    def current_name(self):
        i = self.views.index(self.focus)
        if i < 3:
            return VIEW_NAMES[i]
        bv = self.views[3]
        return VIEW_NAMES[3 + bv.currentIndex()] if isinstance(bv, QTabWidget) else "BEV"

    def show_view(self, name):
        """Make a view the main (single / large) view: Transverse, Coronal, Sagittal, BEV, 3D or Room."""
        i = VIEW_NAMES.index(name)
        if i >= 3 and isinstance(self.views[3], QTabWidget):
            self.views[3].setCurrentIndex(i - 3)
        self.set_focus(self.views[min(i, 3)])
        self._notify()

    def _notify(self):
        for f in self.on_focus:
            f(self.current_name())

    def set_focus(self, v):
        if v is self.focus:
            return
        self.focus = v
        if self.mode != "4":
            self.apply()
        self._notify()

    def set_mode(self, mode):
        self.mode = mode
        self.apply()

    def apply(self):
        for v in self.views:
            self.grid.removeWidget(v); v.hide()
        for r in range(3):
            self.grid.setRowStretch(r, 0); self.grid.setColumnStretch(r, 0)
        if self.mode == "1":
            self.grid.addWidget(self.focus, 0, 0); self.focus.show()
            self.grid.setRowStretch(0, 1); self.grid.setColumnStretch(0, 1)
        elif self.mode == "1+3":
            others = [v for v in self.views if v is not self.focus]
            self.grid.addWidget(self.focus, 0, 0, 3, 1); self.focus.show()
            for r, v in enumerate(others):
                self.grid.addWidget(v, r, 1); v.show(); self.grid.setRowStretch(r, 1)
            self.grid.setColumnStretch(0, 3); self.grid.setColumnStretch(1, 1)
        else:
            for n, v in enumerate(self.views):
                self.grid.addWidget(v, n // 2, n % 2); v.show()
            for r in range(2):
                self.grid.setRowStretch(r, 1); self.grid.setColumnStretch(r, 1)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.state = AppState()
        self.setWindowTitle(f"PyTPS {__version__}")
        self.resize(1500, 900)
        st = self.state
        self.beamviews = BeamViews(st)
        self.views = [SliceView(st, "axial"), SliceView(st, "coronal"), SliceView(st, "sagittal"), self.beamviews]
        self.dose_ov, self.beam_ov = DoseOverlay(st), BeamOverlay(st)
        self.point_ov = PointOverlay(st)
        for v in self.views[:3]:
            v.overlays = [self.dose_ov, self.beam_ov, self.point_ov]
        self.grid = ViewGrid(self.views)
        st.views = self.views

        # workspaces (left)
        self.work = QTabWidget(); self.work.setTabPosition(QTabWidget.North); self.work.setMinimumWidth(330)
        self.patient = PatientPanel(st); self.contour = ContourPanel(st)
        self.work.addTab(self.patient, "Patient")
        self.work.addTab(self.contour, "Contouring")
        self.planning = QTabWidget()
        self.beams_panel = BeamsPanel(st); self.rx_panel = PrescriptionPanel(st)
        self.cost_panel = ConstraintsPanel(st); self.opt_panel = OptimisationPanel(st)
        # each planning tab scrolls when the screen is not high enough, instead of squeezing its controls
        for w_, t_ in ((self.beams_panel, "Beams"), (self.rx_panel, "Prescription"), (self.cost_panel, "IMRT Constraints"),
                       (self.opt_panel, "Optimisation")):
            sc = QScrollArea(); sc.setWidget(w_); sc.setWidgetResizable(True); sc.setFrameShape(QFrame.NoFrame)
            self.planning.addTab(sc, t_)
        self.work.addTab(self.planning, "Planning")
        self.evaluation = EvaluationPanel(st)
        self.work.addTab(self.evaluation, "Evaluation")

        # lower area: DVH / plan summary / log
        self.lower = QTabWidget()
        self.dvh = DVHWidget(st)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumBlockCount(500)
        self.profile = ProfileWidget(st)
        self.lower.addTab(self.dvh, "DVH"); self.lower.addTab(self.profile, "Profile"); self.lower.addTab(self.log, "Messages")
        self.evaluation.dvh_widget = self.dvh

        right = QSplitter(Qt.Vertical); right.addWidget(self.grid); right.addWidget(self.lower)
        right.setStretchFactor(0, 4); right.setStretchFactor(1, 1); right.setSizes([650, 200])
        main = QSplitter(Qt.Horizontal); main.addWidget(self.work); main.addWidget(right)
        main.setStretchFactor(0, 0); main.setStretchFactor(1, 1); main.setSizes([360, 1140])
        self.setCentralWidget(main)

        self._build_actions()
        self.status = QLabel(""); self.statusBar().addWidget(self.status, 1)
        st.message.connect(self._message)
        st.changed.connect(self._changed)

    # ------------------------------------------------------------------ menus and toolbar
    def _act(self, text, slot=None, icon=None, shortcut=None, tip=None, checkable=False):
        a = QAction(text, self)
        if icon is not None:
            a.setIcon(icon)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if tip:
            a.setToolTip(tip); a.setStatusTip(tip)
        a.setCheckable(checkable)
        if slot:
            a.triggered.connect(slot)
        return a

    def _build_actions(self):
        st = self.state
        mb = self.menuBar()
        # File
        m = mb.addMenu("&File")
        self.a_import = self._act("Import DICOM folder…", lambda: (self.work.setCurrentWidget(self.patient), self.patient.choose_folder()), icons.folder(), "Ctrl+O", "Import CT and RT Structure Set from a folder")
        m.addAction(self.a_import)
        pm = m.addMenu(icons.phantom(), "Load practice phantom")
        for n in PHANTOMS:
            pm.addAction(n, lambda n=n: self.patient.load_phantom(n))
        m.addSeparator()
        self.a_export = self._act("Export RT Structure Set…", self.export_rtstruct, icons.save(), "Ctrl+E")
        m.addAction(self.a_export)
        em = m.addMenu(icons.camera(), "Export image / data")
        em.addAction(self._act("Main view as image…", self.save_view_image, shortcut="Ctrl+Shift+P"))
        em.addAction(self._act("Whole window as image…", self.save_screenshot, shortcut="Ctrl+P"))
        em.addSeparator()
        em.addAction("DVH as image…", lambda: self.dvh.save_image())
        em.addAction("DVH data (CSV)…", lambda: self.dvh.save_csv())
        em.addAction("Dose statistics (CSV)…", lambda: self.evaluation.export())
        em.addSeparator()
        em.addAction("Dose profile as image…", lambda: self.profile.save_image())
        em.addAction("Dose profile data (CSV)…", lambda: self.profile.save_csv())
        m.addSeparator(); m.addAction(self._act("Exit", self.close, shortcut="Ctrl+Q"))
        # Edit
        m = mb.addMenu("&Edit")
        m.addAction(self._act("Undo", st.undo, icons.undo(), "Ctrl+Z")); m.addAction(self._act("Redo", st.redo, icons.undo(True), "Ctrl+Y"))
        # View
        m = mb.addMenu("&View")
        lg = QActionGroup(self)
        self.layout_acts = {}
        for key, name, ic in (("4", "2 × 2 views", icons.layout("4")), ("1+3", "One large + three small", icons.layout("3")), ("1", "Single view", icons.layout("1"))):
            a = self._act(name, lambda _=False, k=key: self.grid.set_mode(k), ic, checkable=True); lg.addAction(a); m.addAction(a); self.layout_acts[key] = a
        self.layout_acts["4"].setChecked(True)
        vm = m.addMenu("Main view (single / large)")
        for k, n in enumerate(VIEW_NAMES):
            vm.addAction(self._act(n, lambda _=False, n=n: self.grid.show_view(n), shortcut=f"Alt+{k + 1}"))
        m.addSeparator()
        a = self._act("Dose colour bar / isodose legend", self.show_legend, checkable=True); a.setChecked(True); m.addAction(a)
        wm = m.addMenu("Window / level")
        for n, (lv, w) in WL_PRESETS.items():
            wm.addAction(f"{n} ({w:.0f}/{lv:.0f})", lambda lv=lv, w=w: st.set_window(lv, w))
        m.addAction(self._act("Reset zoom", self.reset_zoom, shortcut="Ctrl+0"))
        # Contouring
        m = mb.addMenu("&Contouring")
        m.addAction(self._act("New structure…", lambda: (self.work.setCurrentWidget(self.contour), self.contour.new()), shortcut="Ctrl+N"))
        m.addAction(self._act("Delete structure", self.contour.delete))
        m.addSeparator()
        for t, f in (("Interpolate", self.contour.interpolate), ("Fill holes", self.contour.fill_holes),
                     ("Keep largest part", self.contour.largest), ("Body outline from CT", self.contour.auto_body)):
            m.addAction(t, lambda f=f: (self.work.setCurrentWidget(self.contour), f()))
        # Planning
        m = mb.addMenu("&Planning")
        self.a_beam = self._act("Add beam", self.add_beam, icons.beam(), "Ctrl+B", "Add a static field at the isocentre")
        self.a_calc = self._act("Calculate dose", self.calculate, icons.calc(), "F5", "Calculate the dose of the plan")
        m.addAction(self.a_beam); m.addAction(self._act("Add arc", lambda: (self.show_planning(0), self.beams_panel.add_arc())))
        m.addAction(self._act("Add opposed beam", lambda: (self.show_planning(0), self.beams_panel.opposed())))
        m.addAction(self._act("Isocentre to target centre", lambda: (self.show_planning(0), self.beams_panel.iso_target(all_beams=True))))
        m.addAction(self._act("Prescription…", lambda: self.show_planning(1)))
        m.addAction(self._act("IMRT constraints…", lambda: self.show_planning(2)))
        m.addSeparator(); m.addAction(self.a_calc)
        m.addAction(self._act("Optimise (Stage 1 + 2)", lambda: (self.show_planning(3), self.opt_panel.both()), shortcut="F6"))
        dm = m.addMenu("Dose display")
        dg = QActionGroup(self)
        for k, n in (("lines", "Isodose lines"), ("wash", "Colour wash"), ("difference", "Difference to the compared plan"), ("off", "Off")):
            a = self._act(n, lambda _=False, k=k: self.set_dose_mode(k), checkable=True); dg.addAction(a); dm.addAction(a)
            if k == "lines":
                a.setChecked(True)
        a = self._act("Show beams in the slices", lambda on: self.show_beams(on), checkable=True); a.setChecked(True); m.addAction(a)
        a = self._act("Show field junctions (overlap / gap)", lambda on: self.show_junctions(on), checkable=True); a.setChecked(True); m.addAction(a)
        # Plan management and DICOM RT
        m = mb.addMenu("Pl&ans")
        for t, f in (("New plan", self.new_plan), ("Copy plan", self.copy_plan), ("Rename plan…", self.rename_plan),
                     ("Delete plan", self.delete_plan), (None, None), ("Plan sum…", self.sum_plans), (None, None),
                     ("Export RT Plan…", self.export_rtplan), ("Export RT Dose…", self.export_rtdose),
                     ("Import RT Plan…", self.import_rtplan), ("Import RT Dose (compare)…", self.import_rtdose), (None, None),
                     ("PDF plan report…", lambda: self.evaluation.report(window=self))):
            if t is None:
                m.addSeparator()
            else:
                m.addAction(t, f)
        # Tools / Help
        m = mb.addMenu("&Tools")
        m.addAction(self._act("Measure distance", lambda: self.set_tool("ruler"), icons.ruler()))
        m.addAction(self._act("Beam data and model…", self.beam_data))
        m = mb.addMenu("&Help")
        m.addAction(self._act("User manual", self.show_manual, shortcut="Shift+F1"))
        m.addAction(self._act("Guided exercise: VMAT-TBI (thesis)", self.show_guide, shortcut="F1"))
        m.addSeparator()
        m.addAction(self._act("About PyTPS", self.about))

        # toolbar
        tb = QToolBar("Main"); tb.setIconSize(QSize(22, 22)); tb.setMovable(False); self.addToolBar(tb)
        tb.addAction(self.a_import)
        b = self._act("Phantom", lambda: self.patient.load_phantom(self.patient.ph.currentText()), icons.phantom(), tip="Load the practice phantom chosen in the Patient panel")
        tb.addAction(b); tb.addAction(self.a_export)
        tb.addSeparator()
        for k in ("4", "1+3", "1"):
            tb.addAction(self.layout_acts[k])
        self.mainview = QComboBox(); self.mainview.addItems(VIEW_NAMES)
        self.mainview.setToolTip("Main view: shown alone in the single layout and large in the one + three layout")
        self.mainview.textActivated.connect(self.grid.show_view); tb.addWidget(self.mainview)
        self.grid.on_focus.append(self._main_view_changed)
        tb.addSeparator()
        self.wl = QComboBox(); self.wl.addItems(list(WL_PRESETS)); self.wl.setToolTip("Window / level preset")
        self.wl.currentTextChanged.connect(lambda n: st.set_window(*WL_PRESETS[n]))
        tb.addWidget(self.wl)
        tb.addSeparator()
        tg = QActionGroup(self)
        self.tool_acts = {}
        for key, name, ic, tip in (("select", "Crosshair", icons.cross(), "Click to move the crosshair (all views follow)"),
                                   ("pan", "Pan", icons.pan(), "Drag to move the image (also: middle mouse button)"),
                                   ("zoom", "Zoom", icons.zoom(), "Drag up / down to zoom (also: Ctrl + wheel)"),
                                   ("window", "Window / level", icons.contrast(), "Drag to change window and level (also: right mouse button)"),
                                   ("ruler", "Measure", icons.ruler(), "Drag to measure a distance"),
                                   ("brush", "Brush", icons.brush(), "Paint the selected structure on the current slice"),
                                   ("eraser", "Eraser", icons.brush(True), "Erase the selected structure on the current slice"),
                                   ("polygon", "Polygon", icons.polygon(), "Click points, double-click to close (Shift = subtract)")):
            a = self._act(name, lambda _=False, k=key: self.set_tool(k), ic, tip=tip, checkable=True)
            tg.addAction(a); tb.addAction(a); self.tool_acts[key] = a
        self.tool_acts["select"].setChecked(True)
        tb.addWidget(QLabel("  Brush "))
        self.bsize = QDoubleSpinBox(); self.bsize.setRange(1, 50); self.bsize.setValue(10); self.bsize.setSuffix(" mm"); self.bsize.setDecimals(0)
        self.bsize.valueChanged.connect(lambda v: setattr(st, "brush_mm", v)); tb.addWidget(self.bsize)
        tb.addSeparator()
        tb.addAction(self._act("Undo", st.undo, icons.undo(), tip="Undo (Ctrl+Z)")); tb.addAction(self._act("Redo", st.redo, icons.undo(True), tip="Redo (Ctrl+Y)"))
        tb.addSeparator()
        tb.addWidget(QLabel(" Plan "))
        self.planbox = QComboBox(); self.planbox.setMinimumWidth(130); self.planbox.setToolTip("Current plan")
        self.planbox.currentIndexChanged.connect(self._plan_selected); tb.addWidget(self.planbox)
        tb.addAction(self.a_beam); tb.addAction(self.a_calc)
        tb.addWidget(QLabel("  CP "))
        self.cpbox = QSpinBox(); self.cpbox.setRange(1, 1); self.cpbox.setToolTip("Control point of the selected arc (BEV, 3D and slices)")
        self.cpbox.valueChanged.connect(self._cp_changed); tb.addWidget(self.cpbox)
        tb.addSeparator()
        tb.addAction(self._act("Screenshot", self.save_screenshot, icons.camera(), tip="Save the window as PNG"))

    # ------------------------------------------------------------------ actions
    def show_guide(self):
        if getattr(self, "guide", None) is None:
            from .guide import GuideDock
            self.guide = GuideDock(self)
            self.addDockWidget(Qt.RightDockWidgetArea, self.guide)
        self.guide.show(); self.guide.raise_()

    def set_tool(self, k):
        self.state.set_tool(k)
        if k in self.tool_acts:
            self.tool_acts[k].setChecked(True)
        if k in ("brush", "eraser", "polygon"):
            self.work.setCurrentWidget(self.contour)

    # ------------------------------------------------------------------ plans
    def _fill_plans(self):
        st = self.state
        self.planbox.blockSignals(True); self.planbox.clear()
        for p in st.plans:
            self.planbox.addItem(p.name)
        if st.plan is not None:
            self.planbox.setCurrentText(st.plan.name)
        self.planbox.blockSignals(False)

    def _plan_selected(self, i):
        st = self.state
        if 0 <= i < len(st.plans) and st.plans[i] is not st.plan:
            self.set_plan(st.plans[i])

    def set_plan(self, p):
        st = self.state
        st.plan = p
        if st.compare is p:
            st.compare = None
        st.cur_beam = p.beams[0].name if p.beams else None; st.cp_index = 0
        self._fill_plans()
        for w in ("plans", "plan", "costs", "dose"):
            st.changed.emit(w)

    def _unique(self, base):
        names = {p.name for p in self.state.plans}
        n, name = 1, base
        while name in names:
            n += 1; name = f"{base} ({n})"
        return name

    def new_plan(self):
        from ..core.plan import Plan
        st = self.state
        if st.image is None:
            return
        p = Plan(self._unique(f"Plan {len(st.plans) + 1}"))
        if st.plan is not None:
            p.rx.target = st.plan.rx.target
        st.plans.append(p); self.set_plan(p)

    def copy_plan(self):
        import copy as _copy
        st = self.state
        if st.plan is None:
            return
        p = _copy.deepcopy(st.plan); p.name = self._unique(st.plan.name + " copy")
        st.plans.append(p); self.set_plan(p)

    def rename_plan(self):
        from PySide6.QtWidgets import QInputDialog
        st = self.state
        if st.plan is None:
            return
        n, ok = QInputDialog.getText(self, "Rename plan", "Name:", text=st.plan.name)
        if ok and n.strip() and n.strip() not in {p.name for p in st.plans}:
            st.plan.name = n.strip(); self._fill_plans(); st.changed.emit("plans")

    def delete_plan(self):
        st = self.state
        if st.plan is None or len(st.plans) < 2:
            return
        if QMessageBox.question(self, "Delete plan", f"Delete {st.plan.name}?") != QMessageBox.Yes:
            return
        st.plans.remove(st.plan); self.set_plan(st.plans[0])

    def sum_plans(self):
        from PySide6.QtWidgets import QInputDialog
        from ..core.plan import plan_sum
        st = self.state
        ok_plans = [p for p in st.plans if p.dose is not None and st.engine is not None and len(p.dose) == len(st.engine.grid.pts)]
        if len(ok_plans) < 2:
            QMessageBox.information(self, "Plan sum", "Two plans with calculated dose (same dose grid) are needed."); return
        names = [p.name for p in ok_plans]
        a, ok = QInputDialog.getItem(self, "Plan sum", "First plan", names, 0, False)
        if not ok:
            return
        b, ok = QInputDialog.getItem(self, "Plan sum", "Second plan", [n for n in names if n != a], 0, False)
        if not ok:
            return
        s = plan_sum(next(p for p in ok_plans if p.name == a), next(p for p in ok_plans if p.name == b))
        s.name = self._unique(s.name); st.plans.append(s); self.set_plan(s)

    def _need_dose(self):
        st = self.state
        if st.plan is None or st.plan.dose is None or st.engine is None:
            QMessageBox.information(self, "DICOM", "Calculate the dose first."); return False
        return True

    def export_rtplan(self):
        from ..core import dicomio
        st = self.state
        if st.plan is None or not st.plan.beams:
            QMessageBox.information(self, "RT Plan", "The plan has no beams."); return
        path, _ = QFileDialog.getSaveFileName(self, "Export RT Plan", f"RP_{st.plan.name}.dcm", "DICOM (*.dcm)")
        if path:
            try:
                dicomio.save_rtplan(path, st.plan, st.image)
                self._message(f"RT Plan written: {os.path.basename(path)}")
            except Exception as e:
                QMessageBox.warning(self, "RT Plan", str(e))

    def export_rtdose(self, path=None):
        from ..core import dicomio
        st = self.state
        if not self._need_dose():
            return
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "Export RT Dose", f"RD_{st.plan.name}.dcm", "DICOM (*.dcm)")
        if path:
            try:
                dicomio.save_rtdose(path, st.engine.grid.to_volume(st.plan.dose), st.engine.grid.spacing, st.engine.grid.origin, st.image)
                self._message(f"RT Dose written: {os.path.basename(path)}")
            except Exception as e:
                QMessageBox.warning(self, "RT Dose", str(e))

    def import_rtplan(self):
        from ..core import dicomio
        from ..core.plan import Plan
        st = self.state
        if st.image is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import RT Plan", "", "DICOM (*.dcm);;All files (*)")
        if not path:
            return
        try:
            beams, rx = dicomio.load_rtplan(path, list(st.models))
        except Exception as e:
            QMessageBox.warning(self, "RT Plan", f"Could not read the plan: {e}"); return
        p = Plan(self._unique("Imported plan")); p.beams = beams
        if rx:
            p.rx.dose, p.rx.fractions = rx
        if st.plan is not None:
            p.rx.target = st.plan.rx.target
        for b in beams:
            b.weight = b.mu if b.mu > 0 else 1.0
        st.plans.append(p); self.set_plan(p)
        self._message(f"Imported {len(beams)} beams. Calculate the dose to see it with the PyTPS beam model.")

    def import_rtdose(self, path=None):
        from ..core import dicomio
        from ..core.dose_pb import DoseEngine
        from ..core.plan import Plan
        from scipy import ndimage
        st = self.state
        if st.image is None:
            return
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Import RT Dose", "", "DICOM (*.dcm);;All files (*)")
        if not path:
            return
        try:
            arr, sp, org = dicomio.load_rtdose(path)
        except Exception as e:
            QMessageBox.warning(self, "RT Dose", f"Could not read the dose: {e}"); return
        if st.engine is None:
            st.engine = DoseEngine(st.ss, st.models, 4.0); st.engine_version = (st.ss.version, st.density_version)
        pts = st.engine.grid.pts
        c = (pts - np.asarray(org)) / np.asarray(sp)
        d = ndimage.map_coordinates(arr, [c[:, 2], c[:, 1], c[:, 0]], order=1, cval=0.0).astype(np.float32)
        p = Plan(self._unique("Imported dose"), kind="imported"); p.dose = d; p.version = 1
        if st.plan is not None:
            p.rx = __import__("copy").deepcopy(st.plan.rx)
        p.rx.dose = float(np.percentile(d[d > 0], 98)) if (d > 0).any() and st.plan is None else p.rx.dose
        st.plans.append(p)
        self._fill_plans(); st.changed.emit("plans")
        self._message("RT Dose imported as a plan; choose it in Evaluation ▸ Compare with, or select it in the plan list.")

    def beam_data(self):
        from .beamdata_dialog import BeamDataDialog
        dlg = BeamDataDialog(self.state, self)
        if dlg.exec():
            st = self.state
            for p in st.plans:
                p.beam_dose.clear()
            self._message("Beam model updated: recalculate the dose of your plans.")

    def show_planning(self, i):
        self.work.setCurrentWidget(self.planning); self.planning.setCurrentIndex(i)

    def add_beam(self):
        self.show_planning(0); self.beams_panel.add_static()

    def calculate(self):
        self.show_planning(1); self.rx_panel.calculate()

    def set_dose_mode(self, k):
        if k == "difference" and self.state.compare is None:
            self._message("Choose a plan in Evaluation ▸ Compare with to show the dose difference")
        self.dose_ov.mode = k
        for v in self.views[:3]:
            v.update()

    def show_junctions(self, on):
        self.beam_ov.junctions = bool(on)
        for v in self.views[:3]:
            v.update()

    def show_beams(self, on):
        self.beam_ov.show = bool(on)
        for v in self.views[:3]:
            v.update()

    def _cp_changed(self, v):
        self.state.cp_index = v - 1
        self.state.changed.emit("beam")

    def _sync_cp(self):
        st = self.state
        b = st.plan.beam(st.cur_beam) if st.plan and st.cur_beam else None
        n = len(b.control_points()) if b is not None and b.kind == "ARC" else 1
        self.cpbox.blockSignals(True); self.cpbox.setRange(1, n); self.cpbox.setValue(min(st.cp_index + 1, n)); self.cpbox.blockSignals(False)
        st.cp_index = self.cpbox.value() - 1

    def reset_zoom(self):
        for v in self.views:
            if isinstance(v, SliceView):
                v.zoom = 1.0; v.pan = v.pan * 0; v.update()

    def export_rtstruct(self):
        st = self.state
        if st.ss is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export RT Structure Set", "RS_PyTPS.dcm", "DICOM (*.dcm)")
        if not path:
            return
        from ..core import dicomio
        try:
            dicomio.save_rtstruct(path, st.ss)
        except Exception as e:
            QMessageBox.warning(self, "Export", str(e)); return
        self._message(f"RT Structure Set written: {os.path.basename(path)}")

    def _main_view_changed(self, name):
        if hasattr(self, "mainview"):
            self.mainview.blockSignals(True); self.mainview.setCurrentText(name); self.mainview.blockSignals(False)

    def show_legend(self, on):
        self.dose_ov.show_legend = bool(on)
        for v in self.views[:3]:
            v.update()

    def save_view_image(self, path=None):
        """Save the main view (the focused slice view, or the BEV / 3D / room view) as PNG."""
        v = self.grid.focus
        w = v.currentWidget() if isinstance(v, QTabWidget) else v
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "Save view as image", f"PyTPS_{self.grid.current_name()}.png", "PNG (*.png);;JPEG (*.jpg)")
        if path:
            w.grab().save(path)
            self._message(f"Image written: {path}")

    def show_manual(self):
        from .manual import ManualDialog
        if getattr(self, "manual", None) is None:
            self.manual = ManualDialog(self)
        self.manual.show(); self.manual.raise_()

    def save_screenshot(self, path=None):
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "Save screenshot", "PyTPS.png", "PNG (*.png)")
        if path:
            self.grab().save(path)

    def about(self):
        QMessageBox.about(self, "About PyTPS",
                          f"<b>PyTPS {__version__}</b><br>Educational radiotherapy treatment planning system for "
                          f"teaching medical physics students.<br><br>"
                          f"Developed by <b>Kazim Radfar</b>, PhD student in Medical Physics.<br><br>"
                          f"{DISCLAIMER}<br><br>Open source under the MIT licence.<br>"
                          f"Source code and user manual: <a href='{SOURCE_URL}'>{SOURCE_URL}</a>")

    def _message(self, text):
        self.status.setText(text)
        if text and not text.startswith("x "):
            self.log.appendPlainText(text)

    def _changed(self, what):
        if what in ("plan", "beam", "image"):
            self._sync_cp()
        if what in ("image", "plan", "plans", "dose"):
            self._fill_plans()
        if what == "image" and self.state.image is not None:
            self.setWindowTitle(f"PyTPS {__version__} — {self.state.image.patient.get('id', '')}")
            self._message(f"Loaded {self.state.source}")
