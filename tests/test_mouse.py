"""Field editing with real mouse events, as a user does it: every jaw, larger and smaller, all layouts."""
import pytest

pytest.importorskip("PySide6")


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _send(app, v, kind, pt, button, buttons):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    gp = v.mapToGlobal(pt.toPoint())
    QApplication.sendEvent(v, QMouseEvent(kind, pt, QPointF(gp), button, buttons, Qt.NoModifier))
    app.processEvents()


def _find_edges(v, step=3):
    """Screen points where each jaw of the current beam can be grabbed in view v."""
    from PySide6.QtCore import QPointF
    found = {}
    for yy in range(4, v.height() - 4, step):
        for xx in range(4, v.width() - 4, step):
            h = v._field_hit(QPointF(xx, yy))
            if h is not None and h[0] == "jaw" and h[2] not in found:
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
    edges = _find_edges(v)
    for jaw, pt in edges.items():
        for sense in (+1, -1):                       # +1 larger field, -1 smaller
            b.x1, b.x2, b.y1, b.y2 = jaws0; b.cps = []
            st.set_cursor(b.iso.copy()); st.changed.emit("beam"); app.processEvents()
            pts = _find_edges(v)
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
