"""Overlays on the slice views: isodose lines / colour wash and divergent beam outlines."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPolygonF, QTransform

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


def _section_polygon(b, cp, ax, c):
    """Field section of one control point in the plane coordinate[ax[2]] = c, as a polygon in view coordinates (mm)."""
    fr = Frame(cp, b.iso, b.orientation)
    pts = _pyramid_section(fr, cp, ax[2], c)
    if len(pts) < 3:
        return None
    q = np.array([[pt[ax[0]], pt[ax[1]]] for pt in pts])
    cen = q.mean(0)
    order = np.argsort(np.arctan2(q[:, 1] - cen[1], q[:, 0] - cen[0]))
    return QPolygonF([QPointF(*q[i]) for i in order])


class BeamOverlay:
    def __init__(self, state):
        self.state = state
        self.show = True
        self.junctions = True        # overlap / gap labels between fields of different isocentres
        self._env = {}               # cache of field envelopes per beam and plane

    def envelope(self, b, ax, c):
        """Region of the plane covered by the field over all its control points (an arc: the whole rotation),
        as a QPainterPath in view coordinates (mm). Cached."""
        key = (b.name, b.kind, b.gantry, b.arc_stop, b.arc_dir, b.cp_spacing, b.collimator, b.couch, b.x1, b.x2, b.y1, b.y2,
               tuple(np.round(b.iso, 1)), b.orientation, len(b.cps), ax[2], round(c, 1))
        key = key + (self._body_key(),)
        if key in self._env:
            return self._env[key]
        cps = b.control_points()
        if b.kind == "ARC":
            k = max(1, len(cps) // 36)
            cps = cps[::k] + ([cps[-1]] if (len(cps) - 1) % k else [])
        path = QPainterPath()
        path.setFillRule(Qt.WindingFill)
        for cp in cps:
            poly = _section_polygon(b, cp, ax, c)
            if poly is not None:
                sub = QPainterPath(); sub.addPolygon(poly); sub.closeSubpath()
                path = path.united(sub)
        band = self._body_band(ax, path.boundingRect())   # only inside the body width (not the far, diverged beam)
        if band is not None and not path.isEmpty():
            clipped = path.intersected(band)
            path = clipped if not clipped.isEmpty() else path
        if len(self._env) > 400:
            self._env.clear()
        self._env[key] = path
        return path

    def _body_key(self):
        st = self.state
        ss = st.ss
        return (id(ss), getattr(ss, "version", 0)) if ss is not None else None

    def _body_bounds(self):
        """(min, max) patient coordinates of the body outline along x, y, z (None without an EXTERNAL structure)."""
        st = self.state
        key = self._body_key()
        if getattr(self, "_bb_key", None) == key:
            return self._bb
        self._bb_key, self._bb = key, None
        ext = st.ss.external() if st.ss is not None else None
        img = st.image
        if ext is None or img is None or ext.mask is None or not ext.mask.any():
            return None
        m = ext.mask
        out = []
        for i, a in enumerate("xyz"):
            other = tuple(k for k in range(3) if k != 2 - i)      # mask axes are (z, y, x)
            idx = np.nonzero(m.any(axis=other))[0]
            ac = img.axis(a)
            out.append((float(ac[idx[0]]), float(ac[idx[-1]])))
        self._bb = out
        return out

    def _body_band(self, ax, br):
        """Clip region: across the body (+1 cm) in the view direction that is not head-foot, over the whole length
        of the field (br: its bounding rectangle) along z."""
        bb = self._body_bounds()
        if bb is None or 2 not in ax[:2]:
            return None
        k = ax[:2].index(2)
        lo, hi = bb[ax[1 - k]]
        lo, hi = lo - 10, hi + 10
        r = QPainterPath()
        if k == 1:
            r.addRect(QRectF(lo, br.top() - 10, hi - lo, br.height() + 20))
        else:
            r.addRect(QRectF(br.left() - 10, lo, br.width() + 20, hi - lo))
        return r

    @staticmethod
    def _transform(S):
        p00, p10, p01 = S(0.0, 0.0), S(1.0, 0.0), S(0.0, 1.0)
        return QTransform(p10.x() - p00.x(), p10.y() - p00.y(), p01.x() - p00.x(), p01.y() - p00.y(), p00.x(), p00.y())

    def junction_data(self, ax, c):
        """Junctions between the fields of neighbouring isocentres along the head-foot direction (z), measured in the
        plane coordinate[ax[2]] = c including the divergence: [(z_lo, z_hi, overlap_mm, side, names_a, names_b)];
        a negative overlap is a gap. Empty if the view has no z axis or there is only one isocentre."""
        st = self.state
        if st.plan is None or 2 not in ax[:2]:
            return []
        k = ax[:2].index(2)                       # which view axis is z
        groups = {}
        for b in st.plan.beams:
            if not b.visible:
                continue
            env = self.envelope(b, ax, c)
            if env.isEmpty():
                continue
            key = tuple(np.round(b.iso, 0))
            g = groups.setdefault(key, {"path": QPainterPath(), "names": [], "iso": b.iso})
            g["path"] = g["path"].united(env); g["names"].append(b.name)
        if len(groups) < 2:
            return []
        boxes = []
        for g in groups.values():
            full = g["path"].boundingRect()
            u0 = float(g["iso"][ax[1 - k]])                 # measured on the line through the isocentre
            strip = QPainterPath()
            if k == 1:
                strip.addRect(QRectF(u0 - 2, full.top() - 10, 4, full.height() + 20))
            else:
                strip.addRect(QRectF(full.left() - 10, u0 - 2, full.width() + 20, 4))
            line = g["path"].intersected(strip)
            lr = line.boundingRect() if not line.isEmpty() else full
            # z range from the isocentre line, the other direction from the whole field (for placing the label)
            r = QRectF(full.left(), lr.top(), full.width(), lr.height()) if k == 1 else QRectF(lr.left(), full.top(), lr.width(), full.height())
            lo, hi = (r.left(), r.right()) if k == 0 else (r.top(), r.bottom())
            olo, ohi = (r.top(), r.bottom()) if k == 0 else (r.left(), r.right())
            boxes.append((lo, hi, olo, ohi, g["names"]))
        boxes.sort(key=lambda t: (t[0] + t[1]) / 2)
        out = []
        for a_, b_ in zip(boxes[:-1], boxes[1:]):
            lo, hi = max(a_[0], b_[0]), min(a_[1], b_[1])
            out.append((lo, hi, hi - lo, max(a_[3], b_[3]) + 8, a_[4], b_[4]))
        return out

    def _junctions(self, p, view, S, ax, c, tf):
        data = self.junction_data(ax, c)
        if not data:
            return
        k = ax[:2].index(2)
        f = p.font(); f.setBold(True); p.setFont(f)
        for lo, hi, ov, side, _na, _nb in data:
            col = QColor(90, 220, 140) if ov > 0 else QColor(255, 80, 80)
            p.setPen(QPen(col, 2))
            if k == 1:
                p1, p2 = tf.map(QPointF(side, lo)), tf.map(QPointF(side, hi))
            else:
                p1, p2 = tf.map(QPointF(lo, side)), tf.map(QPointF(hi, side))
            p.drawLine(p1, p2)
            for q in (p1, p2):
                if k == 1:
                    p.drawLine(q + QPointF(-4, 0), q + QPointF(4, 0))
                else:
                    p.drawLine(q + QPointF(0, -4), q + QPointF(0, 4))
            mid = (p1 + p2) / 2
            p.drawText(mid + QPointF(8, 4), f"overlap {ov / 10:.1f} cm" if ov > 0 else f"GAP {-ov / 10:.1f} cm")
        f.setBold(False); p.setFont(f)

    def __call__(self, p, view):
        st = self.state
        if not self.show or st.plan is None or not st.plan.beams:
            return
        _, S, _ = view.mapping()
        ax = view._ax()
        n, c = ax[2], float(st.cursor[ax[2]])
        tf = self._transform(S)
        for bi, b in enumerate(st.plan.beams):
            if not b.visible:
                continue
            col = QColor(*BEAM_COLORS[bi % len(BEAM_COLORS)])
            cur = b.name == st.cur_beam
            cps = b.control_points()
            show = cps if b.kind != "ARC" else [cps[min(st.cp_index, len(cps) - 1)]] if cur else []
            if b.kind == "ARC" and 2 in ax[:2]:   # coronal/sagittal: whole region covered during the rotation
                env = self.envelope(b, ax, c)
                if not env.isEmpty():
                    fill = QColor(col); fill.setAlpha(34 if cur else 24)
                    edge = QColor(col); edge.setAlpha(230 if cur else 170)
                    p.setBrush(QBrush(fill)); p.setPen(QPen(edge, 2.0 if cur else 1.4, Qt.SolidLine))
                    p.drawPath(tf.map(env)); p.setBrush(Qt.NoBrush)
                    r = tf.map(env).boundingRect()
                    p.setPen(edge); p.drawText(r.topLeft() + QPointF(4, 13), b.name)
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
        if self.junctions:
            self._junctions(p, view, S, ax, c, tf)


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
