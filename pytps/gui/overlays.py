"""Overlays on the slice views: isodose lines / colour wash and divergent beam outlines."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF

from ..core.beams import SAD, Frame

ISODOSE = [(107, (255, 45, 85)), (105, (255, 140, 26)), (100, (255, 225, 77)), (95, (76, 217, 100)), (90, (46, 197, 255)),
           (80, (61, 123, 255)), (70, (130, 110, 255)), (50, (180, 107, 255)), (30, (120, 130, 150))]
BEAM_COLORS = [(255, 159, 67), (88, 166, 255), (61, 220, 151), (255, 107, 154), (201, 160, 255), (255, 215, 94), (92, 225, 230)]


class DoseOverlay:
    def __init__(self, state):
        self.state = state
        self.mode = "lines"         # lines, wash, off
        self.levels = {lv: True for lv, _ in ISODOSE}
        self.show_legend = True     # colour bar / isodose legend in each slice view
        self._cache = {}

    def _has_dose(self):
        st = self.state
        return not (self.mode == "off" or st.plan is None or st.plan.dose is None or st.engine is None
                    or len(st.plan.dose) != len(st.engine.grid.pts) or st.plan.rx.dose <= 0)

    def legend(self, p, view):
        """Colour bar (wash), isodose legend (lines) or difference scale, drawn at the top right of the view."""
        if not self.show_legend or not self._has_dose():
            return
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QFont, QLinearGradient
        st = self.state
        rx = st.plan.rx.dose
        small = view.height() < 380 or view.width() < 480     # compact legend (per cent only) in small views
        row = 11 if small else 15
        f = QFont(view.font()); f.setPointSizeF(7.0 if small else 8.5); p.setFont(f)
        W = 58 if small else 112
        x0 = view.width() - W - 20
        y0 = 22
        if self.mode == "difference":
            if st.compare is None:
                return
            H = 8 * row
            p.fillRect(QRectF(x0 - 6, y0 - 4, W + 6, H + 2 * row + 8), QColor(0, 0, 0, 150))
            p.setPen(QColor(232, 238, 245)); p.drawText(QPointF(x0, y0 + row - 3), "Difference")
            bar = QRectF(x0, y0 + row + 2, 12, H)
            g = QLinearGradient(bar.topLeft(), bar.bottomLeft())
            g.setColorAt(0.0, QColor(255, 0, 0)); g.setColorAt(0.47, QColor(255, 190, 57, 90))
            g.setColorAt(0.5, QColor(0, 0, 0, 0)); g.setColorAt(0.53, QColor(60, 200, 255, 90)); g.setColorAt(1.0, QColor(0, 60, 255))
            p.fillRect(bar, g); p.setPen(QColor(150, 160, 175)); p.drawRect(bar)
            p.setPen(QColor(232, 238, 245))
            for frac, lab in ((0.0, "+10 %"), (0.5, "0"), (1.0, "−10 %")):
                yy = bar.top() + frac * bar.height()
                gy = {0.0: 0.1 * rx, 0.5: 0.0, 1.0: -0.1 * rx}[frac]
                p.drawText(QPointF(x0 + 18, yy + 4), f"{lab}  {gy:+.2f} Gy" if (frac != 0.5 and not small) else lab)
            return
        levels = [(lv, col) for lv, col in ISODOSE if self.mode == "wash" or self.levels.get(lv, True)]
        H = row * (len(levels) + 1) + 6
        p.fillRect(QRectF(x0 - 6, y0 - 4, W + 6, H + 4), QColor(0, 0, 0, 150))
        p.setPen(QColor(232, 238, 245))
        p.drawText(QPointF(x0, y0 + row - 3), f"Rx {rx:.3g} Gy" if small else (f"Rx {rx:.2f} Gy" if rx < 10 else f"Rx {rx:.1f} Gy"))
        for i, (lv, col) in enumerate(levels):
            yy = y0 + row * (i + 1) + 3
            sw = 10 if small else 14
            if self.mode == "wash":
                p.fillRect(QRectF(x0, yy, sw, row - 2), QColor(*col))
            else:
                p.setPen(QPen(QColor(*col), 2)); p.drawLine(QPointF(x0, yy + row / 2 - 1), QPointF(x0 + sw, yy + row / 2 - 1))
            p.setPen(QColor(232, 238, 245))
            gy = rx * lv / 100
            p.drawText(QPointF(x0 + (16 if small else 20), yy + row - 4), f"{lv:>3d} %")
            if not small:
                p.drawText(QPointF(x0 + 62, yy + row - 4), f"{gy:.1f} Gy" if gy >= 10 else f"{gy:.2f} Gy")

    def _plane(self, view):
        st = self.state
        plan, eng = st.plan, st.engine
        g = eng.grid
        cmp = st.compare if self.mode == "difference" else None
        key = (id(plan), plan.version, id(cmp), cmp.version if cmp is not None else 0, self.mode == "difference", view.view, round(float(st.cursor[view._ax()[2]]), 2))
        if key in self._cache:
            return self._cache[key]
        if len(self._cache) > 30:
            self._cache.clear()
        vol = g.to_volume(plan.dose)
        if cmp is not None and cmp.dose is not None and len(cmp.dose) == len(plan.dose):
            vol = vol - g.to_volume(cmp.dose)
        n = view._ax()[2]
        f = (st.cursor[n] - g.origin[n]) / g.spacing
        k0 = int(np.clip(np.floor(f), 0, vol.shape[2 - n] - 1)); k1 = min(k0 + 1, vol.shape[2 - n] - 1); t = float(np.clip(f - k0, 0, 1))
        take = (lambda k: vol[k]) if n == 2 else (lambda k: vol[:, k, :]) if n == 1 else (lambda k: vol[:, :, k])
        sl = take(k0) * (1 - t) + take(k1) * t
        u, v = view._ax()[0], view._ax()[1]
        res = (sl, g.origin[u], g.origin[v], g.spacing)
        self._cache[key] = res
        return res

    def __call__(self, p, view):
        st = self.state
        if not self._has_dose():
            return
        sl, u0, v0, h = self._plane(view)
        rx = st.plan.rx.dose
        if rx <= 0 or not sl.any():
            return
        _, S, _ = view.mapping()
        if self.mode == "difference":
            from PySide6.QtCore import QRectF
            from PySide6.QtGui import QImage
            f = np.clip(sl / (0.1 * rx), -1, 1)
            rgba = np.zeros(sl.shape + (4,), np.uint8)
            pos, neg = f > 0.05, f < -0.05
            rgba[pos] = np.stack([np.full(pos.sum(), 255), (200 * (1 - f[pos])).astype(np.uint8), (60 * (1 - f[pos])).astype(np.uint8), (60 + 150 * f[pos]).astype(np.uint8)], -1)
            rgba[neg] = np.stack([(60 * (1 + f[neg])).astype(np.uint8), (140 * (1 + f[neg]) + 60).astype(np.uint8), np.full(neg.sum(), 255), (60 - 150 * f[neg]).astype(np.uint8)], -1)
            img = QImage(rgba.data, sl.shape[1], sl.shape[0], sl.shape[1] * 4, QImage.Format_RGBA8888).copy()
            a = S(u0 - h / 2, v0 - h / 2); b = S(u0 + (sl.shape[1] - 0.5) * h, v0 + (sl.shape[0] - 0.5) * h)
            if view._ax()[3] < 0:
                img = img.mirrored(False, True)
            p.drawImage(QRectF(min(a.x(), b.x()), min(a.y(), b.y()), abs(b.x() - a.x()), abs(b.y() - a.y())), img)
            p.setPen(QColor(255, 200, 200)); p.drawText(8, 46, f"Dose difference: {st.plan.name} − {st.compare.name if st.compare else '?'}")
            return
        if self.mode == "wash":
            from PySide6.QtGui import QImage
            f = sl / rx
            rgba = np.zeros(sl.shape + (4,), np.uint8)
            for lv, col in sorted(ISODOSE):
                m = f >= lv / 100
                rgba[m] = (*col, 110)
            img = QImage(rgba.data, sl.shape[1], sl.shape[0], sl.shape[1] * 4, QImage.Format_RGBA8888).copy()
            a = S(u0 - h / 2, v0 - h / 2); b = S(u0 + (sl.shape[1] - 0.5) * h, v0 + (sl.shape[0] - 0.5) * h)
            from PySide6.QtCore import QRectF
            tgt = QRectF(min(a.x(), b.x()), min(a.y(), b.y()), abs(b.x() - a.x()), abs(b.y() - a.y()))
            if view._ax()[3] < 0:
                img = img.mirrored(False, True)
            p.drawImage(tgt, img)
            return
        from skimage import measure
        for lv, col in ISODOSE:
            if not self.levels.get(lv, True):
                continue
            p.setPen(QPen(QColor(*col), 1.4))
            for c in measure.find_contours(sl, rx * lv / 100):
                pts = [S(u0 + q[1] * h, v0 + q[0] * h) for q in c[::1 if len(c) < 300 else 2]]
                p.drawPolyline(QPolygonF(pts))


def _pyramid_section(fr: Frame, cp, axis_n, c):
    """Intersection of the divergent field pyramid with the plane coordinate[axis_n] = c (patient coordinates)."""
    S = fr.iso + fr.source
    far = SAD + 700
    corners = [fr.ray_point(np.array(u), np.array(v), np.array(far)) for u, v in ((cp.x1, cp.y1), (cp.x2, cp.y1), (cp.x2, cp.y2), (cp.x1, cp.y2))]
    edges = [(S, q) for q in corners] + [(corners[i], corners[(i + 1) % 4]) for i in range(4)]
    pts = []
    for a, b in edges:
        da, db = a[axis_n] - c, b[axis_n] - c
        if da == db:
            continue
        if da * db <= 0:
            t = da / (da - db)
            pts.append(a + t * (b - a))
    return pts


class BeamOverlay:
    def __init__(self, state):
        self.state = state
        self.show = True

    def __call__(self, p, view):
        st = self.state
        if not self.show or st.plan is None or not st.plan.beams:
            return
        _, S, _ = view.mapping()
        ax = view._ax()
        n, c = ax[2], float(st.cursor[ax[2]])
        for bi, b in enumerate(st.plan.beams):
            if not b.visible:
                continue
            col = QColor(*BEAM_COLORS[bi % len(BEAM_COLORS)])
            cur = b.name == st.cur_beam
            cps = b.control_points()
            show = cps if b.kind != "ARC" else [cps[min(st.cp_index, len(cps) - 1)]] if cur else []
            if b.kind == "ARC":           # arc: central axes of all control points, faint
                col2 = QColor(col); col2.setAlpha(70 if cur else 40)
                p.setPen(QPen(col2, 1))
                for cp in cps[::max(1, len(cps) // 45)]:
                    fr = Frame(cp, b.iso, b.orientation)
                    s3 = b.iso + fr.source * 0.32
                    if abs(s3[n] - c) < 30 and abs(b.iso[n] - c) < 30:
                        p.drawLine(S(s3[ax[0]], s3[ax[1]]), S(b.iso[ax[0]], b.iso[ax[1]]))
            for cp in show:
                fr = Frame(cp, b.iso, b.orientation)
                pts = _pyramid_section(fr, cp, n, c)
                if len(pts) >= 3:
                    q = np.array([[pt[ax[0]], pt[ax[1]]] for pt in pts])
                    cen = q.mean(0); order = np.argsort(np.arctan2(q[:, 1] - cen[1], q[:, 0] - cen[0]))
                    poly = QPolygonF([S(*q[i]) for i in order])
                    fill = QColor(col); fill.setAlpha(38 if cur else 18)
                    p.setBrush(QBrush(fill)); edge = QColor(col); edge.setAlpha(230 if cur else 140)
                    p.setPen(QPen(edge, 2.0 if cur else 1.2)); p.drawPolygon(poly)
                    p.setBrush(Qt.NoBrush)
                # central axis (dashed) when it lies close to this plane
                src = b.iso + fr.source
                if abs(fr.axis[n]) < 0.2 and abs(b.iso[n] - c) < 40:
                    end = b.iso + fr.axis * 400
                    p.setPen(QPen(col, 1.2, Qt.DashLine))
                    p.drawLine(S(src[ax[0]], src[ax[1]]), S(end[ax[0]], end[ax[1]]))
                    lab = b.iso + fr.source * 0.2
                    p.setPen(col); p.drawText(S(lab[ax[0]], lab[ax[1]]) + QPointF(4, -4), f"{b.name}  G{cp.gantry:.0f}")
            # rotation handles of the current beam (gantry, arc stop, collimator, couch): drag them to rotate
            if cur and hasattr(view, "_rot_handles"):
                q0 = S(b.iso[ax[0]], b.iso[ax[1]])
                for key, g, hp in view._rot_handles(b):
                    faint = QColor(col); faint.setAlpha(110)
                    p.setPen(QPen(faint, 1, Qt.DotLine)); p.drawLine(q0, hp)
                    p.setPen(QPen(QColor(255, 255, 255), 1.5)); p.setBrush(QBrush(col))
                    if key == "gantry":
                        p.drawEllipse(hp, 6.5, 6.5)
                    elif key == "stop":
                        p.drawRect(QRectF(hp.x() - 5.5, hp.y() - 5.5, 11, 11))
                    elif key == "collimator":
                        p.drawPolygon(QPolygonF([hp + QPointF(0, -7.5), hp + QPointF(7.5, 0), hp + QPointF(0, 7.5), hp + QPointF(-7.5, 0)]))
                    else:
                        p.drawPolygon(QPolygonF([hp + QPointF(0, -7.5), hp + QPointF(7, 6), hp + QPointF(-7, 6)]))
                    p.setBrush(Qt.NoBrush)
                    p.setPen(col)
                    lab = {"gantry": "G", "stop": "stop", "collimator": "Col", "couch": "Couch"}[key]
                    p.drawText(hp + QPointF(9, -7), f"{lab} {g:.0f}°")
            # isocentre marker
            if abs(b.iso[n] - c) < 3:
                q = S(b.iso[ax[0]], b.iso[ax[1]])
                p.setPen(QPen(QColor(255, 80, 80), 2)); p.drawLine(q + QPointF(-7, 0), q + QPointF(7, 0)); p.drawLine(q + QPointF(0, -7), q + QPointF(0, 7))


class PointOverlay:
    def __init__(self, state):
        self.state = state

    def __call__(self, p, view):
        st = self.state
        if not st.points:
            return
        _, S, _ = view.mapping()
        ax = view._ax()
        for name, xyz in st.points:
            if abs(xyz[ax[2]] - st.cursor[ax[2]]) > 3:
                continue
            q = S(xyz[ax[0]], xyz[ax[1]])
            p.setPen(QPen(QColor(255, 255, 255), 1.6)); p.setBrush(Qt.NoBrush); p.drawEllipse(q, 5, 5)
            p.drawText(q + QPointF(7, -6), name)
