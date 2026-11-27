"""Start PyTPS:  python -m pytps  [--phantom NAME] [--dicom FOLDER] [--layout 4|1+3|1] [--screenshot FILE]"""
from __future__ import annotations

import argparse
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pytps", description="PyTPS - educational treatment planning (not for clinical use)")
    ap.add_argument("--phantom", help="load a practice phantom at start, e.g. 'Thorax (lung tumour)'")
    ap.add_argument("--dicom", help="folder with DICOM CT (and RT Structure Set) to load at start")
    ap.add_argument("--layout", choices=["4", "1+3", "1"], default="4")
    ap.add_argument("--workspace", default="", help="workspace tab to show (Patient, Contouring, Planning, Evaluation)")
    ap.add_argument("--tool", default="", help="toolbar tool to select")
    ap.add_argument("--size", default="1500x900", help="window size WxH")
    ap.add_argument("--demo-plan", default="", help="add demo beams and calculate, e.g. '0,90,180,270' (gantry angles)")
    ap.add_argument("--dose-mode", default="lines", choices=["lines", "wash", "difference", "off"])
    ap.add_argument("--optimise", type=int, default=0, help="with --demo-plan: optimise the beams (Stage 1 iterations)")
    ap.add_argument("--arc", action="store_true", help="with --demo-plan: use one arc instead of static fields")
    ap.add_argument("--guide-tbi", action="store_true", help="open the VMAT-TBI guided exercise and do all steps (demo)")
    ap.add_argument("--beam-tab", default="", help="BEV, 3D or Room")
    ap.add_argument("--main-view", default="", help="main view: Transverse, Coronal, Sagittal, BEV, 3D or Room")
    ap.add_argument("--export", default="", help="with --demo-plan: write DVH/profile images and CSV files with this prefix (for tests)")
    ap.add_argument("--screenshot", help="save a screenshot after start and quit (for tests)")
    ap.add_argument("--self-test", dest="self_test", help="run a short check of the installed program and write the result (JSON)")
    ap.add_argument("--self-test-gui", dest="self_test_gui",
                    help="check mouse editing of fields with real mouse events, as a user does it (JSON report)")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test(a.self_test)
    if a.self_test_gui:
        return self_test_gui(a.self_test_gui)

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from .gui.main_window import MainWindow
    from .gui.theme import apply_theme

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("PyTPS")
    apply_theme(app)
    _set_icon(app)
    w = MainWindow()
    _install_error_log(w)
    W, H = (int(v) for v in a.size.lower().split("x"))
    w.resize(W, H)
    w.show()
    if a.phantom:
        w.patient.load_phantom(a.phantom)
    if a.dicom:
        w.patient.choose_folder(a.dicom)
        w.patient.load_selected()
    if a.demo_plan and w.state.image is not None:
        from .gui.planning import demo_beams
        demo_beams(w.state, [float(g) for g in a.demo_plan.split(",")])
        if a.arc:
            b = w.state.plan.beams[0]; b.kind = "ARC"; b.gantry, b.arc_stop = 181.0, 179.0
            del w.state.plan.beams[1:]
        if a.optimise:
            for b in w.state.plan.beams:
                b.mlc_mode = "optimised"; b.x1 -= 5; b.x2 += 5; b.y1 -= 5; b.y2 += 5
            w.rx_panel.refresh(); w.rx_panel.store()
            w.opt_panel.it1.setValue(a.optimise); w.opt_panel.it2.setValue(max(10, a.optimise // 3))
            w.opt_panel.both()
        else:
            w.rx_panel.refresh(); w.rx_panel.calculate()
        w.set_dose_mode(a.dose_mode)
    if a.guide_tbi:
        w.show_guide()
        for k in range(7):
            w.guide.run(k)
    if a.beam_tab:
        i = {"bev": 0, "3d": 1, "room": 2}.get(a.beam_tab.lower(), 0)
        w.beamviews.setCurrentIndex(i)
    w.grid.set_mode(a.layout)
    if a.main_view:
        w.grid.show_view(a.main_view)
    if a.export and w.state.plan is not None and w.state.plan.dose is not None:
        w.dvh.save_image(a.export + "_dvh.png"); w.dvh.save_csv(a.export + "_dvh.csv")
        w.profile.save_image(a.export + "_profile.png"); w.profile.save_csv(a.export + "_profile.csv")
    if a.workspace:
        for i in range(w.work.count()):
            if w.work.tabText(i).lower() == a.workspace.lower():
                w.work.setCurrentIndex(i)
    if a.tool:
        w.set_tool(a.tool)
    if a.screenshot:
        def shot():
            w.save_screenshot(a.screenshot)
            app.quit()
        QTimer.singleShot(1500, shot)
    return app.exec()


def _set_icon(app):
    import os
    from PySide6.QtGui import QIcon
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "pytps.png")
    if os.path.exists(p):
        app.setWindowIcon(QIcon(p))


def _install_error_log(window):
    """Unexpected errors are shown in the status bar / Messages tab and written to ~/.pytps/pytps.log.
    (The Windows program has no console, so without this an error would be invisible.)"""
    import datetime
    import os
    import traceback
    log = os.path.join(os.path.expanduser("~"), ".pytps", "pytps.log")

    def hook(t, v, tb):
        text = "".join(traceback.format_exception(t, v, tb))
        try:
            os.makedirs(os.path.dirname(log), exist_ok=True)
            with open(log, "a", encoding="utf-8") as fh:
                fh.write(f"--- {datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n{text}\n")
        except OSError:
            pass
        try:
            window.state.message.emit(f"Error: {t.__name__}: {v} (details in {log})")
        except Exception:
            pass
        if sys.stderr is not None:
            sys.__excepthook__(t, v, tb)
    sys.excepthook = hook


def self_test(out_path):
    """Load a phantom, add two beams, calculate, optimise briefly, write a JSON report. Exit code 0 = passed."""
    import json
    import os
    import time
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from .gui.main_window import MainWindow
    from .gui.planning import demo_beams
    from . import __version__
    t0 = time.time()
    res = {"version": __version__, "ok": False}
    try:
        app = QApplication.instance() or QApplication([])
        w = MainWindow(); w.resize(1366, 768); w.show()
        w.patient.load_phantom("Pelvis (prostate)")
        demo_beams(w.state, [0, 120, 240])
        for b in w.state.plan.beams:
            b.mlc_mode = "optimised"
        w.rx_panel.refresh(); w.rx_panel.method.setCurrentText("mean"); w.rx_panel.store()
        w.opt_panel.it1.setValue(15); w.opt_panel.it2.setValue(5)
        w.opt_panel.both()
        p = w.state.plan
        from .core.plan import dvh
        d = dvh(p, w.state.engine, "PTV")
        res.update(mu=[round(b.mu, 1) for b in p.beams], ptv_mean=round(d["mean"], 2), seconds=round(time.time() - t0, 1))
        res["ok"] = bool(abs(d["mean"] - p.rx.dose) < 0.05 * p.rx.dose and all(b.mu > 0 for b in p.beams))
        w.close()
    except Exception as e:  # pragma: no cover
        import traceback
        res["error"] = repr(e); res["trace"] = traceback.format_exc()
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    return 0 if res["ok"] else 1


def self_test_gui(out_path):
    """Add a beam like a user (Beams tab), then resize it and move the isocentre with real mouse events in the
    transverse, coronal and sagittal views. Uses the normal platform (a window is shown). Exit code 0 = passed."""
    import json
    import traceback
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    from .gui.main_window import MainWindow
    from .gui.theme import apply_theme
    from . import __version__
    errors = []
    old_hook = sys.excepthook
    sys.excepthook = lambda t, v, tb: errors.append("".join(traceback.format_exception(t, v, tb)))
    res = {"version": __version__, "frozen": bool(getattr(sys, "frozen", False)), "ok": False, "views": {}}
    try:
        app = QApplication.instance() or QApplication(sys.argv[:1])
        apply_theme(app)
        res["platform"] = app.platformName()
        w = MainWindow(); w.resize(1366, 768); w.show(); app.processEvents()
        w.patient.load_phantom("Pelvis (prostate)")
        w.show_planning(0); w.beams_panel.add_static(); app.processEvents()
        st = w.state
        b = st.plan.beams[0]
        res["beam"] = {"name": b.name, "gantry": b.gantry, "jaws": [b.x1, b.x2, b.y1, b.y2], "iso": [float(x) for x in b.iso]}
        st.set_cursor(b.iso.copy()); app.processEvents()

        def send(v, kind, pt, buttons):
            gp = v.mapToGlobal(pt.toPoint())
            ev = QMouseEvent(kind, pt, QPointF(gp), Qt.LeftButton if kind != QEvent.MouseMove else Qt.NoButton,
                             buttons, Qt.NoModifier)
            QApplication.sendEvent(v, ev); app.processEvents()

        ok_all = True
        for name, v in zip(("Transverse", "Coronal", "Sagittal"), w.views[:3]):
            r = {}
            found = None
            for yy in range(4, v.height() - 4, 2):           # find a jaw edge of the beam in this view
                for xx in range(4, v.width() - 4, 2):
                    h = v._field_hit(QPointF(xx, yy))
                    if h is not None and h[0] == "jaw":
                        found = (QPointF(xx, yy), h); break
                if found:
                    break
            if found is None:
                r["hit"] = None; ok_all = False; res["views"][name] = r; continue
            pt, h = found
            jaw = h[2]
            before = getattr(b, jaw)
            send(v, QEvent.MouseMove, pt, Qt.NoButton)
            r["hover_cursor"] = str(v.cursor().shape())
            send(v, QEvent.MouseButtonPress, pt, Qt.LeftButton)
            r["drag_state"] = str(v._drag[:2]) if v._drag else None
            for k in range(1, 6):                            # drag outwards by 30 px in 5 steps
                q = QPointF(pt.x() + 6 * k, pt.y() + 6 * k)
                send(v, QEvent.MouseMove, q, Qt.LeftButton)
            send(v, QEvent.MouseButtonRelease, q, Qt.NoButton)
            after = getattr(b, jaw)
            r.update(hit=list(h), point=[pt.x(), pt.y()], before=before, after=after, changed=bool(abs(after - before) >= 1))
            ok_all &= r["changed"]
            res["views"][name] = r
        res["errors"] = errors
        res["ok"] = bool(ok_all and not errors)
        w.close()
    except Exception as e:  # pragma: no cover
        res["error"] = repr(e); res["trace"] = traceback.format_exc(); res["errors"] = errors
    finally:
        sys.excepthook = old_hook
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
