"""Planning workspace: beams table and beam properties, prescription and dose calculation."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDial, QDoubleSpinBox, QFormLayout, QGroupBox,
                               QHBoxLayout, QHeaderView, QLabel, QMessageBox, QProgressDialog, QPushButton, QSpinBox,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..core.beams import Beam, Wedge, opposing
from ..core.dose_pb import DoseEngine
from ..core.plan import Plan, calculate, normalise

COLS = ["Beam", "Energy", "Type", "Gantry", "Stop", "Coll", "Couch", "X1", "X2", "Y1", "Y2", "MLC", "Wedge", "Weight", "MU"]
NUM = {"Gantry": "gantry", "Stop": "arc_stop", "Coll": "collimator", "Couch": "couch", "X1": "x1", "X2": "x2", "Y1": "y1",
       "Y2": "y2", "Weight": "weight"}
CM = {"x1", "x2", "y1", "y2"}          # shown in cm, stored in mm


def _dspin(lo, hi, dec=1, val=0.0, step=1.0, suffix=""):
    s = QDoubleSpinBox(); s.setRange(lo, hi); s.setDecimals(dec); s.setSingleStep(step); s.setValue(val)
    if suffix:
        s.setSuffix(suffix)
    return s


def ensure_plan(state):
    if state.plan is None:
        state.plan = Plan(f"Plan {len(state.plans) + 1}")
        state.plans.append(state.plan)
        cands = [s for s in state.ss.structures if s.is_target and s.mask.any()] if state.ss else []
        tgt = next((s.name for s in cands if s.type == "PTV"), cands[0].name if cands else None)
        if tgt:
            state.plan.rx.target = tgt
    return state.plan


def target_centre(state, name=None):
    s = state.ss.get(name or ensure_plan(state).rx.target) if state.ss else None
    if s is None or not s.mask.any():
        return np.array(state.cursor, float)
    k, j, i = [float(np.mean(a)) for a in np.nonzero(s.mask)]
    return state.image.index_to_world((i, j, k))


class BeamsPanel(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self._filling = False
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        for t, f, tip in (("Add beam", self.add_static, "New static field at the isocentre"), ("Add arc", self.add_arc, "New arc"),
                          ("Copy", self.copy_beam, "Copy the selected beam"), ("Opposed", self.opposed, "Add the parallel-opposed beam"),
                          ("Delete", self.delete, "Delete the selected beam")):
            b = QPushButton(t); b.setToolTip(tip); b.clicked.connect(f); row.addWidget(b)
        lay.addLayout(row)
        self.table = QTableWidget(0, len(COLS)); self.table.setHorizontalHeaderLabels(COLS)
        self.table.verticalHeader().hide(); self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.itemChanged.connect(self._edited); self.table.itemSelectionChanged.connect(self._selected)
        self.table.setMinimumHeight(150)
        lay.addWidget(self.table, 1)
        note = QLabel("Angles in degrees; jaws in cm at the isocentre. Gantry 0 = anterior, 90 = patient's left (HFS).")
        note.setWordWrap(True); note.setStyleSheet("color:#6b7785;font-size:11px"); lay.addWidget(note)

        g = QGroupBox("Isocentre (cm)")
        gl = QHBoxLayout(g)
        self.iso = [_dspin(-200, 200, 2, 0, 0.1) for _ in range(3)]
        for lab, s in zip("xyz", self.iso):
            gl.addWidget(QLabel(lab)); gl.addWidget(s)
        lay.addWidget(g)
        r2 = QHBoxLayout()
        for t, f, tip in (("Apply", self.apply_iso, "Isocentre from the x, y, z values"),
                          ("Crosshair", self.iso_cursor, "Isocentre at the crosshair"),
                          ("Target centre", self.iso_target, "Isocentre at the centre of the target")):
            b = QPushButton(t); b.setToolTip(tip); b.clicked.connect(f); r2.addWidget(b)
        self.iso_all = QCheckBox("all beams")
        self.iso_all.setToolTip("Unticked: only the selected beam gets the new isocentre (e.g. separate fields for TBI).\n"
                                "Ticked: every beam of the plan.")
        r2.addWidget(self.iso_all)
        lay.addLayout(r2)

        g2 = QGroupBox("Selected beam")
        f2 = QFormLayout(g2)
        # gantry dial: turn it with the mouse (drag or wheel); 0° at the top as seen from the foot of the couch
        gw = QWidget(); gl2 = QHBoxLayout(gw); gl2.setContentsMargins(0, 0, 0, 0)
        self.gdial = QDial(); self.gdial.setRange(0, 359); self.gdial.setWrapping(True); self.gdial.setNotchesVisible(True)
        self.gdial.setNotchTarget(15); self.gdial.setFixedSize(56, 56)
        self.gdial.setToolTip("Turn to rotate the gantry of the selected beam (or drag the round handle in the transverse view)")
        self.gspin = _dspin(0, 359, 0, 0, 1, " °"); self.gspin.setWrapping(True)
        self.gdial.valueChanged.connect(lambda v: self._gantry((v + 180) % 360, final=not self.gdial.isSliderDown()))
        self.gdial.sliderReleased.connect(lambda: self._gantry(None, final=True))
        self.gspin.valueChanged.connect(lambda v: self._gantry(v, final=True))
        gl2.addWidget(self.gdial); gl2.addWidget(self.gspin); gl2.addStretch(1)
        f2.addRow("Gantry", gw)
        cw = QWidget(); cl = QHBoxLayout(cw); cl.setContentsMargins(0, 0, 0, 0)
        self.cspin = _dspin(0, 359, 0, 0, 1, " °"); self.cspin.setWrapping(True)
        self.kspin = _dspin(0, 359, 0, 0, 1, " °"); self.kspin.setWrapping(True)
        self.cspin.setToolTip("Collimator angle (mouse wheel, arrows, or the diamond handle in the view that faces the beam)")
        self.kspin.setToolTip("Couch angle (mouse wheel, arrows, or the triangle handle in the coronal view)")
        self.cspin.valueChanged.connect(lambda v: self._angle("collimator", v))
        self.kspin.valueChanged.connect(lambda v: self._angle("couch", v))
        cl.addWidget(QLabel("Coll")); cl.addWidget(self.cspin); cl.addWidget(QLabel("Couch")); cl.addWidget(self.kspin); cl.addStretch(1)
        f2.addRow("", cw)
        self.mlc_target = QComboBox(); self.mlc_margin = _dspin(-20, 50, 1, 5, 0.5, " mm")
        self.mlc_target.currentTextChanged.connect(lambda t: self._set("mlc_target", t)); self.mlc_margin.valueChanged.connect(lambda v: self._set("mlc_margin", v))
        f2.addRow("MLC fits to", self.mlc_target); f2.addRow("MLC margin", self.mlc_margin)
        self.wdir = QComboBox(); self.wdir.addItems(["+X", "-X", "+Y", "-Y"]); self.wdir.currentTextChanged.connect(self._wedge_dir)
        f2.addRow("Wedge thick end", self.wdir)
        self.arcdir = QComboBox(); self.arcdir.addItems(["CW", "CCW"]); self.arcdir.currentTextChanged.connect(lambda t: self._set("arc_dir", t))
        self.cpsp = _dspin(1, 30, 0, 4, 1, " °"); self.cpsp.valueChanged.connect(lambda v: self._set("cp_spacing", v))
        f2.addRow("Arc direction", self.arcdir); f2.addRow("Control point spacing", self.cpsp)
        self.orient = QComboBox(); self.orient.addItems(["HFS", "FFS", "HFP", "FFP"]); self.orient.currentTextChanged.connect(lambda t: self._set("orientation", t))
        f2.addRow("Patient position", self.orient)
        self.ssd = QLabel("—"); f2.addRow("SSD (central axis)", self.ssd)
        lay.addWidget(g2)
        state.changed.connect(self._changed)

    # ------------------------------------------------------------------ helpers
    def plan(self):
        return ensure_plan(self.state)

    def cur(self):
        p = self.plan()
        return p.beam(self.state.cur_beam) if self.state.cur_beam else None

    def _changed(self, what):
        if what in ("image", "plan", "dose", "structures"):
            self.refresh()
        elif what == "beam":
            self._sync_gantry(self.cur())

    def _angle(self, attr, v):
        if self._filling:
            return
        b = self.cur()
        if b is None:
            return
        setattr(b, attr, float(v) % 360); b.cps = []
        if self.state.plan is not None:
            self.state.plan.beam_dose.pop(b.name, None)
        self.state.changed.emit("plan")

    def _sync_gantry(self, b):
        if b is None:
            return
        for w, v in ((self.gdial, int(round(b.gantry + 180)) % 360), (self.gspin, round(b.gantry) % 360),
                     (self.cspin, round(b.collimator) % 360), (self.kspin, round(b.couch) % 360)):
            if w.value() != v:
                w.blockSignals(True); w.setValue(v); w.blockSignals(False)

    def _gantry(self, g, final):
        """Gantry of the selected beam from the dial or the spin box; while the dial turns only the views follow,
        the table is updated when it is released."""
        if self._filling:
            return
        b = self.cur()
        if b is None:
            return
        if g is not None:
            b.gantry = float(g) % 360; b.cps = []
            if self.state.plan is not None:
                self.state.plan.beam_dose.pop(b.name, None)
            self._sync_gantry(b)
            self.state.message.emit(f"{b.name}: gantry {b.gantry:.0f}°")
        self.state.changed.emit("plan" if final else "beam")

    def refresh(self):
        st = self.state
        if st.image is None:
            return
        p = self.plan()
        self._filling = True
        self.table.setRowCount(len(p.beams))
        for r, b in enumerate(p.beams):
            vals = {"Beam": b.name, "Gantry": f"{b.gantry:.1f}", "Stop": f"{b.arc_stop:.1f}" if b.kind == "ARC" else "",
                    "Coll": f"{b.collimator:.1f}", "Couch": f"{b.couch:.1f}", "X1": f"{b.x1 / 10:.1f}", "X2": f"{b.x2 / 10:.1f}",
                    "Y1": f"{b.y1 / 10:.1f}", "Y2": f"{b.y2 / 10:.1f}", "Weight": f"{b.weight:.3f}", "MU": f"{b.mu:.1f}" if b.mu else "–"}
            for c, name in enumerate(COLS):
                if name in ("Energy", "Type", "MLC", "Wedge"):
                    cb = QComboBox()
                    opts = {"Energy": list(st.models), "Type": ["STATIC", "ARC"], "MLC": ["open", "conformal", "manual", "optimised"], "Wedge": ["0", "15", "30", "45", "60"]}[name]
                    cb.addItems(opts)
                    cb.setCurrentText({"Energy": b.energy, "Type": b.kind, "MLC": b.mlc_mode, "Wedge": str(int(b.wedge.angle))}[name])
                    cb.currentTextChanged.connect(lambda t, b=b, name=name: self._combo(b, name, t))
                    self.table.setCellWidget(r, c, cb)
                else:
                    it = QTableWidgetItem(vals.get(name, ""))
                    if name == "MU" or (name == "Stop" and b.kind != "ARC"):
                        it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter) if name != "Beam" else None
                    self.table.setItem(r, c, it)
            if b.name == st.cur_beam:
                self.table.selectRow(r)
        if not st.cur_beam and p.beams:
            st.cur_beam = p.beams[0].name
        names = st.ss.names() if st.ss else []
        keep = self.mlc_target.currentText(); self.mlc_target.blockSignals(True); self.mlc_target.clear(); self.mlc_target.addItems(["(target)"] + names)
        b = self.cur()
        if b is not None:
            self.mlc_target.setCurrentText(b.mlc_target or "(target)")
            for s, v in zip(self.iso, b.iso):
                s.blockSignals(True); s.setValue(v / 10); s.blockSignals(False)
            self._sync_gantry(b)
            for w, val in ((self.mlc_margin, b.mlc_margin), (self.cpsp, b.cp_spacing)):
                w.blockSignals(True); w.setValue(val); w.blockSignals(False)
            for w, val in ((self.wdir, b.wedge.direction), (self.arcdir, b.arc_dir), (self.orient, b.orientation)):
                w.blockSignals(True); w.setCurrentText(val); w.blockSignals(False)
            eng = st.engine
            if eng is not None:
                s = eng.ssd(b)
                self.ssd.setText("outside the body" if not np.isfinite(s) else f"{s / 10:.1f} cm")
        else:
            self.mlc_target.setCurrentText(keep)
        self.mlc_target.blockSignals(False)
        self._filling = False

    def _touch(self, b=None):
        st = self.state
        if b is not None and st.plan is not None:
            st.plan.beam_dose.pop(b.name, None)
        st.changed.emit("plan")

    def _set(self, attr, val):
        if self._filling:
            return
        b = self.cur()
        if b is None:
            return
        if attr == "mlc_target" and val == "(target)":
            val = ""
        setattr(b, attr, val); b.cps = []
        self._touch(b)

    def _wedge_dir(self, t):
        b = self.cur()
        if b is not None and not self._filling:
            b.wedge = Wedge(b.wedge.angle, t, b.wedge.factor); self._touch(b)

    def _combo(self, b, name, t):
        if self._filling:
            return
        if name == "Energy":
            b.energy = t
        elif name == "Type":
            b.kind = t
            if t == "ARC" and b.arc_stop == b.gantry:
                b.gantry, b.arc_stop = 181.0, 179.0
        elif name == "MLC":
            b.mlc_mode = t
            if t == "manual" and b.left is None:
                from ..core.beams import LEAF_CENTRES
                b.left = np.full(len(LEAF_CENTRES), b.x1); b.right = np.full(len(LEAF_CENTRES), b.x2)
            if t == "open":
                b.left = b.right = None
        elif name == "Wedge":
            b.wedge = Wedge(float(t), b.wedge.direction, 1.0)
        b.cps = []
        self._touch(b)

    def _edited(self, it):
        if self._filling:
            return
        p = self.plan()
        b = p.beams[it.row()]
        col = COLS[it.column()]
        if col == "Beam":
            new = it.text().strip()
            if new and p.beam(new) is None:
                if b.name in p.beam_dose:
                    p.beam_dose[new] = p.beam_dose.pop(b.name)
                if self.state.cur_beam == b.name:
                    self.state.cur_beam = new
                b.name = new
            self.state.changed.emit("plan"); return
        attr = NUM.get(col)
        if not attr:
            return
        try:
            v = float(it.text().replace(",", "."))
        except ValueError:
            self.refresh(); return
        if attr in CM:
            v *= 10
        if attr in ("gantry", "arc_stop", "collimator", "couch"):
            v %= 360
        if attr in ("x1", "y1"):
            v = min(v, getattr(b, "x2" if attr == "x1" else "y2")); v = max(v, -200)
        if attr in ("x2", "y2"):
            v = max(v, getattr(b, "x1" if attr == "x2" else "y1")); v = min(v, 200)
        if attr == "weight":
            v = max(0.0, v)
        setattr(b, attr, v); b.cps = []
        if attr == "weight" and b.name in p.beam_dose and self.state.engine is not None:
            normalise(p, self.state.engine); self.state.changed.emit("dose"); return
        self._touch(b)

    def _selected(self):
        if self._filling:
            return
        rows = self.table.selectionModel().selectedRows()
        if rows:
            self.state.cur_beam = self.plan().beams[rows[0].row()].name
            self.state.changed.emit("beam")
            self._filling = True
            self.refresh()
            self._filling = False

    # ------------------------------------------------------------------ actions
    def _iso_default(self):
        """A new beam starts at the isocentre of the selected beam (then drag its isocentre to move it)."""
        p = self.plan()
        cur = self.cur()
        return (cur or p.beams[0]).iso.copy() if p.beams else target_centre(self.state)

    def _add(self, b):
        p = self.plan()
        if p.beams:
            b.orientation = p.beams[0].orientation
        else:
            b.orientation = self.state.image.orientation if self.state.image.orientation in ("HFS", "FFS", "HFP", "FFP") else "HFS"
        p.beams.append(b); self.state.cur_beam = b.name
        self._touch()

    def add_static(self):
        if self.state.image is None:
            return
        p = self.plan()
        b = Beam(p.new_name("B"), self._iso_default(), energy=next(iter(self.state.models)))
        b.mlc_mode = "conformal"
        self._add(b)

    def add_arc(self):
        if self.state.image is None:
            return
        p = self.plan()
        b = Beam(p.new_name("Arc"), self._iso_default(), energy=next(iter(self.state.models)), kind="ARC", gantry=181.0, arc_stop=179.0)
        b.mlc_mode = "conformal"
        self._add(b)

    def copy_beam(self):
        b = self.cur()
        if b is not None:
            c = b.copy(self.plan().new_name(b.name.rstrip("0123456789") or "B")); c.mu = 0; self._add(c)

    def opposed(self):
        b = self.cur()
        if b is not None:
            c = opposing(b); c.name = self.plan().new_name(b.name.rstrip("0123456789") or "B"); c.mu = 0; self._add(c)

    def delete(self):
        p = self.plan(); b = self.cur()
        if b is None:
            return
        p.beams.remove(b); p.beam_dose.pop(b.name, None)
        self.state.cur_beam = p.beams[0].name if p.beams else None
        if self.state.engine is not None:
            normalise(p, self.state.engine)
        self.state.changed.emit("dose")

    def _set_iso(self, pos, all_beams=None):
        """New isocentre for the selected beam, or for every beam ("all beams" ticked, or all_beams=True)."""
        p = self.plan()
        if all_beams is None:
            all_beams = self.iso_all.isChecked()
        cur = self.cur()
        beams = p.beams if (all_beams or cur is None) else [cur]
        for b in beams:
            b.iso = np.array(pos, float); b.cps = []
            p.beam_dose.pop(b.name, None)
        self.state.changed.emit("plan")

    def apply_iso(self):
        self._set_iso([s.value() * 10 for s in self.iso])

    def iso_cursor(self):
        self._set_iso(self.state.cursor)

    def iso_target(self, all_beams=None):
        self._set_iso(target_centre(self.state), all_beams)


class PrescriptionPanel(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        lay = QVBoxLayout(self)
        g = QGroupBox("Prescription"); f = QFormLayout(g)
        self.dose = _dspin(0.1, 200, 2, 60, 1, " Gy"); self.fx = QSpinBox(); self.fx.setRange(1, 60); self.fx.setValue(30)
        self.per = QLabel("2.00 Gy / fraction")
        self.target = QComboBox()
        self.method = QComboBox(); self.method.addItems(["isocentre", "mean", "D95", "D50"])
        self.method.setToolTip("isocentre: dose at the isocentre; mean / D95 / D50: dose in the target volume")
        self.pct = _dspin(50, 120, 1, 100, 1, " %")
        for w in (self.dose, self.fx):
            w.valueChanged.connect(lambda *_: self.per.setText(f"{self.dose.value() / self.fx.value():.2f} Gy / fraction"))
        f.addRow("Total dose", self.dose); f.addRow("Fractions", self.fx); f.addRow("", self.per)
        f.addRow("Target", self.target); f.addRow("Normalise to", self.method); f.addRow("Prescription isodose", self.pct)
        lay.addWidget(g)
        g2 = QGroupBox("Dose calculation"); f2 = QFormLayout(g2)
        self.grid = _dspin(2, 10, 1, 4, 0.5, " mm"); f2.addRow("Dose grid", self.grid)
        self.grid.valueChanged.connect(lambda v: setattr(self.state, "grid_mm", v))
        self.algo = QLabel("Pencil beam (fluence convolution, radiological depth)"); self.algo.setWordWrap(True); f2.addRow("Algorithm", self.algo)
        self.calc = QPushButton("Calculate dose"); self.calc.setStyleSheet("font-weight:600"); self.calc.clicked.connect(self.calculate)
        f2.addRow(self.calc)
        self.info = QLabel(""); self.info.setWordWrap(True); f2.addRow(self.info)
        lay.addWidget(g2)
        lay.addStretch(1)
        state.changed.connect(lambda w: self.refresh() if w in ("image", "structures") else None)

    def refresh(self):
        st = self.state
        if st.ss is None:
            return
        p = ensure_plan(st)
        self.target.blockSignals(True); self.target.clear(); self.target.addItems(st.ss.names()); self.target.setCurrentText(p.rx.target); self.target.blockSignals(False)
        self.dose.setValue(p.rx.dose); self.fx.setValue(p.rx.fractions); self.method.setCurrentText(p.rx.method); self.pct.setValue(p.rx.percent)
        e = st.image.extent(); big = max(b - a for a, b in e)
        if big > 800 and self.grid.value() < 8:
            self.grid.setValue(8.0)
        elif big > 600 and self.grid.value() < 5:
            self.grid.setValue(6.0)

    def store(self):
        p = ensure_plan(self.state)
        p.rx.dose, p.rx.fractions = self.dose.value(), self.fx.value()
        p.rx.target, p.rx.method, p.rx.percent = self.target.currentText(), self.method.currentText(), self.pct.value()

    def calculate(self):
        st = self.state
        if st.ss is None:
            return
        self.store()
        p = ensure_plan(st)
        if not p.beams:
            QMessageBox.information(self, "Dose", "Add at least one beam in the Beams tab."); return
        if st.engine is None or abs(st.engine.grid.spacing - self.grid.value()) > 1e-6 or st.engine_version != (st.ss.version, st.density_version):
            st.engine = DoseEngine(st.ss, st.models, self.grid.value()); st.engine_version = (st.ss.version, st.density_version)
            p.beam_dose.clear()
        todo = [b.name for b in p.beams if b.name not in p.beam_dose]
        dlg = QProgressDialog("Calculating dose…", None, 0, max(1, len(todo)), self); dlg.setWindowModality(Qt.WindowModal); dlg.show()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            calculate(p, st.engine, lambda n, t, name: (dlg.setValue(n), dlg.setLabelText(f"Calculating {name}…"), QApplication.processEvents()), only=todo)
        except Exception as e:
            QMessageBox.warning(self, "Dose", f"Calculation failed: {e}"); return
        finally:
            QApplication.restoreOverrideCursor(); dlg.close()
        tot = sum(b.mu for b in p.beams)
        self.info.setText(f"Done. Total {tot:.0f} MU per fraction for {p.rx.per_fraction:.2f} Gy (normalised to {p.rx.method}).")
        st.changed.emit("dose")
        st.message.emit(f"Dose calculated: {len(p.beams)} beams, {tot:.0f} MU / fraction")


def fit_jaws_to_mlc(beam, margin=5.0):
    """Jaws around the open leaves (conformal / manual MLC)."""
    from ..core.beams import LEAF_EDGES
    if beam.left is None:
        return
    open_ = np.where(beam.right - beam.left > 0.5)[0]
    if not len(open_):
        return
    beam.x1 = float(max(-200, np.floor(beam.left[open_].min() - margin)))
    beam.x2 = float(min(200, np.ceil(beam.right[open_].max() + margin)))
    beam.y1 = float(max(-200, LEAF_EDGES[open_[0]] - margin))
    beam.y2 = float(min(200, LEAF_EDGES[open_[-1] + 1] + margin))


def demo_beams(state, angles=(0, 90, 180, 270), energy="6X", margin=7.0):
    """A simple conformal plan at the target centre (used by the demo / screenshots)."""
    from ..core.plan import prepare_mlc
    p = ensure_plan(state)
    iso = target_centre(state)
    for g in angles:
        b = Beam(p.new_name("B"), iso.copy(), energy=energy, gantry=float(g), x1=-100, x2=100, y1=-100, y2=100)
        b.mlc_mode = "conformal"; b.mlc_margin = margin
        p.beams.append(b)
    eng = DoseEngine(state.ss, state.models, 4.0)
    prepare_mlc(p, eng)
    for b in p.beams:
        fit_jaws_to_mlc(b)
    state.engine, state.engine_version = eng, (state.ss.version, state.density_version)
    state.cur_beam = p.beams[0].name
    state.changed.emit("plan")
