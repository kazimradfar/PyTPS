"""Field editing with real mouse events, as a user does it: every jaw, larger and smaller, all layouts."""
import pytest

pytest.importorskip("PySide6")


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _send(app, v, kind, pt, button, buttons, mods=None):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    gp = v.mapToGlobal(pt.toPoint())
    QApplication.sendEvent(v, QMouseEvent(kind, pt, QPointF(gp), button, buttons, Qt.NoModifier if mods is None else mods))
    app.processEvents()


def _find_edges(v, step=4, beam=None):
    """Screen points where each jaw of the beam (default: the selected beam) can be grabbed in view v."""
    from PySide6.QtCore import QPointF
    beam = beam or v.state.cur_beam
    found = {}
    for yy in range(4, v.height() - 4, step):
        for xx in range(4, v.width() - 4, step):
            h = v._field_hit(QPointF(xx, yy))
            if h is not None and h[0] == "jaw" and h[1] == beam and h[2] not in found:
                found[h[2]] = QPointF(xx, yy)
        if len(found) == 4:
            break
    return found


def _drag(app, v, pt, dx, dy):
    from PySide6.QtCore import QEvent, QPointF, Qt
    _send(app, v, QEvent.MouseMove, pt, Qt.NoButton, Qt.NoButton)
    _send(app, v, QEvent.MouseButtonPress, pt, Qt.LeftButton, Qt.LeftButton)
    started = v._drag is not None and v._drag[0] == "field"
    q = pt
    for k in range(1, 6):
        q = QPointF(pt.x() + dx * k / 5, pt.y() + dy * k / 5)
        _send(app, v, QEvent.MouseMove, q, Qt.NoButton, Qt.LeftButton)
    _send(app, v, QEvent.MouseButtonRelease, q, Qt.LeftButton, Qt.NoButton)
    return started


def _check_view(app, w, v, b, results, tag):
    """Grab every visible jaw edge; drag it outwards and inwards by 24 px; the jaw must follow."""
    import numpy as np
    from pytps.core.beams import Frame
    st = w.state
    jaws0 = (b.x1, b.x2, b.y1, b.y2)
    st.set_cursor(b.iso.copy()); st.changed.emit("beam"); app.processEvents()
    edges = _find_edges(v, beam=b.name)
    for jaw, pt in edges.items():
        for sense in (+1, -1):                       # +1 larger field, -1 smaller
            b.x1, b.x2, b.y1, b.y2 = jaws0; b.cps = []
            st.set_cursor(b.iso.copy()); st.changed.emit("beam"); app.processEvents()
            h = v._field_hit(pt)
            if h is None or h[1] != b.name or h[2] != jaw:              # the layout may have changed after the last click
                pts = _find_edges(v, beam=b.name)
                if jaw not in pts:
                    results.append((tag, jaw, sense, "edge lost")); continue
                pt = pts[jaw]
            # screen direction in which this jaw moves outwards
            cps = b.control_points(); fr = Frame(cps[0], b.iso, b.orientation)
            ax = fr.X if jaw[0] == "x" else fr.Y
            a = v._ax(); _, S, _ = v.mapping()
            p0 = S(b.iso[a[0]], b.iso[a[1]]); p1 = S(b.iso[a[0]] + 10 * ax[a[0]], b.iso[a[1]] + 10 * ax[a[1]])
            d = np.array([p1.x() - p0.x(), p1.y() - p0.y()]); d = d / (np.linalg.norm(d) + 1e-9)
            out = 1 if jaw.endswith("2") else -1
            dx, dy = d * 24 * out * sense
            before = getattr(b, jaw)
            started = _drag(app, v, pt, dx, dy)
            after = getattr(b, jaw)
            larger = (after - before) * out
            ok = started and (larger > 2 if sense > 0 else larger < -2)
            results.append((tag, jaw, sense, "ok" if ok else f"FAILED started={started} {before:.0f}->{after:.0f}"))
    b.x1, b.x2, b.y1, b.y2 = jaws0; b.cps = []
    return edges


@pytest.mark.parametrize("layout", ["4", "1+3", "1"])
def test_drag_every_jaw_real_mouse(layout):
    from pytps.gui.main_window import MainWindow
    app = _app()
    w = MainWindow(); w.resize(1500, 900); w.show(); app.processEvents()
    w.patient.load_phantom("Pelvis (prostate)")
    w.show_planning(0)
    w.beams_panel.add_static()                        # B1, gantry 0, MLC conformal (as a user adds it)
    w.beams_panel.add_static()                        # B2
    p = w.state.plan
    p.beams[1].gantry = 90.0
    w.state.cur_beam = "B2"; w.state.changed.emit("beam"); app.processEvents()
    w.grid.set_mode(layout); app.processEvents()
    results, seen = [], {}
    for name in ("Transverse", "Coronal", "Sagittal"):
        if layout != "4":
            w.grid.show_view(name); app.processEvents()
        v = w.views[("Transverse", "Coronal", "Sagittal").index(name)]
        b = p.beam(w.state.cur_beam)
        seen[name] = sorted(_check_view(app, w, v, b, results, f"{layout}/{name}/{b.name}"))
    if layout == "1+3":                               # a small view: pressing must still grab the edge
        w.grid.show_view("Transverse"); app.processEvents()
        v = w.views[1]
        b = p.beam(w.state.cur_beam)
        _check_view(app, w, v, b, results, f"{layout}/Coronal-small/{b.name}")
    for r in results:
        print(r)
    print("edges found:", seen)
    failed = [r for r in results if r[3] != "ok"]
    assert results and not failed, failed
    w.close()


def _rotate(app, v, b, key, target):
    """Drag the rotation handle `key` of beam b in view v to the angle `target` with real mouse events."""
    import numpy as np
    from PySide6.QtCore import QEvent, QPointF, Qt
    kind = "gantry" if key == "stop" else key
    h = {k: hp for k, _a, hp in v._rot_handles(b)}
    assert key in h, (key, list(h))
    hp = h[key]
    q0, d0, d90, ok = v._rot_dirs(b, kind)
    R = np.hypot(hp.x() - q0.x(), hp.y() - q0.y())
    t = np.radians(target); d = np.cos(t) * d0 + np.sin(t) * d90
    end = QPointF(q0.x() + R * d[0], q0.y() + R * d[1])
    _send(app, v, QEvent.MouseMove, hp, Qt.NoButton, Qt.NoButton)
    _send(app, v, QEvent.MouseButtonPress, hp, Qt.LeftButton, Qt.LeftButton)
    assert v._drag is not None and v._drag[1] == "rot"
    for k in range(1, 9):
        f = k / 8
        mid = QPointF((1 - f) * hp.x() + f * end.x(), (1 - f) * hp.y() + f * end.y())
        _send(app, v, QEvent.MouseMove, mid, Qt.NoButton, Qt.LeftButton)
    _send(app, v, QEvent.MouseButtonRelease, end, Qt.LeftButton, Qt.NoButton)
    attr = {"gantry": "gantry", "stop": "arc_stop", "collimator": "collimator", "couch": "couch"}[key]
    got = getattr(b, attr)
    assert abs(((got - target) + 180) % 360 - 180) <= 1.0, (key, target, got)


def test_rotate_in_three_views():
    from pytps.gui.main_window import MainWindow
    app = _app()
    w = MainWindow(); w.resize(1500, 900); w.show(); app.processEvents()
    w.patient.load_phantom("Pelvis (prostate)")
    w.show_planning(0)
    w.beams_panel.add_static()
    st = w.state; b = st.plan.beams[0]
    st.set_cursor(b.iso.copy()); app.processEvents()
    tv, cor, sag = w.views[:3]
    keys = lambda v: [h[0] for h in v._rot_handles(b)]
    # gantry 0 (AP field): gantry turns in the transverse view, the collimator in the coronal view (facing the beam)
    assert keys(tv) == ["gantry"] and keys(cor) == ["collimator"] and keys(sag) == []
    for target in (45.0, 270.0, 90.0):
        _rotate(app, tv, b, "gantry", target)
    assert w.beams_panel.gspin.value() == 90
    # gantry 90 (lateral field): collimator in the sagittal view, couch in the coronal view
    assert keys(sag) == ["collimator"] and keys(cor) == ["couch"]
    _rotate(app, sag, b, "collimator", 30.0)
    _rotate(app, cor, b, "couch", 20.0)
    assert w.beams_panel.cspin.value() == 30 and w.beams_panel.kspin.value() == 20
    # an arc has a stop handle; the dial and the spin boxes turn the selected beam
    w.beams_panel.add_arc(); a = st.plan.beam(st.cur_beam); app.processEvents()
    assert [h[0] for h in tv._rot_handles(a)] == ["gantry", "stop"]
    _rotate(app, tv, a, "stop", 200.0)
    w.beams_panel.gdial.setValue((30 + 180) % 360); app.processEvents()
    assert abs(a.gantry - 30) < 0.5
    w.beams_panel.cspin.setValue(15); w.beams_panel.kspin.setValue(350); app.processEvents()
    assert a.collimator == 15 and a.couch == 350
    w.close()


def test_move_fields_separately_for_tbi():
    import numpy as np
    from PySide6.QtCore import QEvent, QPointF, Qt
    from pytps.gui.main_window import MainWindow
    app = _app()
    w = MainWindow(); w.resize(1500, 900); w.show(); app.processEvents()
    w.patient.load_phantom("Pelvis (prostate)")
    w.show_planning(0)
    bp = w.beams_panel
    bp.add_static(); bp.add_static(); bp.add_static()       # B1, B2, B3 at the same isocentre
    st = w.state; p = st.plan
    b1, b2, b3 = p.beams
    iso0 = b1.iso.copy()
    assert np.allclose(b2.iso, iso0) and np.allclose(b3.iso, iso0)
    st.set_cursor(iso0.copy()); app.processEvents()
    cor = w.views[1]
    a = cor._ax(); _, S, _ = cor.mapping()

    def drag_iso(beam_now_at, dy, mods=None):
        q = S(beam_now_at[a[0]], beam_now_at[a[1]])
        _send(app, cor, QEvent.MouseMove, q, Qt.NoButton, Qt.NoButton)
        _send(app, cor, QEvent.MouseButtonPress, q, Qt.LeftButton, Qt.LeftButton, mods)
        assert cor._drag is not None and cor._drag[1] == "iso"
        for k in range(1, 6):
            _send(app, cor, QEvent.MouseMove, QPointF(q.x(), q.y() + dy * k / 5), Qt.NoButton, Qt.LeftButton, mods)
        _send(app, cor, QEvent.MouseButtonRelease, QPointF(q.x(), q.y() + dy), Qt.LeftButton, Qt.NoButton, mods)

    # the selected beam (B3) moves alone: the other fields stay
    drag_iso(iso0, 80)
    assert not np.allclose(b3.iso, iso0) and np.allclose(b1.iso, iso0) and np.allclose(b2.iso, iso0)
    assert abs(b3.iso[2] - iso0[2]) > 20 and abs(b3.iso[0] - iso0[0]) < 2
    # grabbing B1/B2's isocentre selects that beam; with Ctrl both beams that share it move together
    st.cur_beam = "B1"; app.processEvents()
    drag_iso(iso0, -80, Qt.ControlModifier)
    assert np.allclose(b1.iso, b2.iso) and not np.allclose(b1.iso, iso0)
    assert st.cur_beam == "B1"
    # a field edge of a beam that is not selected can be grabbed too (and selects it)
    st.cur_beam = "B3"; app.processEvents()
    h = None
    for yy in range(4, cor.height() - 4, 4):
        for xx in range(4, cor.width() - 4, 4):
            r = cor._field_hit(QPointF(xx, yy))
            if r is not None and r[0] == "jaw" and r[1] == "B1":
                h = QPointF(xx, yy); break
        if h is not None:
            break
    assert h is not None
    _send(app, cor, QEvent.MouseButtonPress, h, Qt.LeftButton, Qt.LeftButton)
    _send(app, cor, QEvent.MouseButtonRelease, h, Qt.LeftButton, Qt.NoButton)
    assert st.cur_beam == "B1"
    # isocentre buttons: only the selected beam unless "all beams" is ticked
    st.cur_beam = "B2"; bp.refresh()
    st.set_cursor(iso0 + np.array([0, 0, -60.0])); bp.iso_all.setChecked(False); bp.iso_cursor()
    assert np.allclose(b2.iso, st.cursor) and not np.allclose(b1.iso, b2.iso)
    bp.iso_all.setChecked(True); bp.iso_cursor()
    assert all(np.allclose(q.iso, b2.iso) for q in p.beams)
    w.close()
