import cv2
import numpy as np
from PyQt5.QtWidgets import QWidget, QSizePolicy
from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont

from ..pipeline.track.display import DisplayStatus, DisplayState, TrackTelemetry


class CameraView(QWidget):
    """Camera FOV — pure black viewport matching New GUI Design (Main Window.pdf)."""

    def __init__(self, title="Camera FOV", parent=None):
        super().__init__(parent)
        self.title = title
        self._rgb = None
        self._w = 640
        self._h = 480
        self._detection = None
        self._estimate = None
        self._est_trail = []
        self._meta = {}
        self._centre_offset = None
        self._display = None      # DisplayState from pipeline.track.display
        self._telemetry = None    # TrackTelemetry for the primary track
        self.show_grid = False
        self.setMinimumSize(400, 340)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: black; border: none;")

    def set_frame(self, frame_gray, detection=None, estimate=None, world_camera=None,
                  show_overlays=True, meta=None, centre_offset=None,
                  display=None, telemetry=None, display_status=None):
        if frame_gray is None:
            return
        h, w = frame_gray.shape[:2]
        self._w, self._h = w, h
        self._detection = detection
        self._estimate = estimate
        self._meta = meta or {}
        self._centre_offset = centre_offset
        # DisplayState + TrackTelemetry computed by DisplayTracker in app.py.
        # (display_status is the legacy tuple form; display wins if both given.)
        if display is None and display_status is not None:
            try:
                _k, _l, _h, _c = display_status
                display = DisplayState(status=DisplayStatus(_k), label=_l,
                                       color_hex=_h, show_no_target=bool(_c))
            except Exception:
                display = None
        self._display = display
        self._telemetry = telemetry
        if estimate is not None and getattr(estimate, "pos_px", None):
            try:
                self._est_trail.append(tuple(estimate.pos_px))
                if len(self._est_trail) > 32:
                    self._est_trail.pop(0)
            except Exception:
                pass
        if len(frame_gray.shape) == 3:
            rgb = cv2.cvtColor(frame_gray, cv2.COLOR_BGR2RGB)
        else:
            rgb = cv2.cvtColor(frame_gray, cv2.COLOR_GRAY2RGB)
        self._rgb = rgb
        self.update()

    def clear(self):
        self._rgb = None
        self._detection = None
        self._estimate = None
        self._est_trail.clear()
        self._meta = {}
        self._centre_offset = None
        self._display = None
        self._telemetry = None
        self.update()

    def _draw_tag(self, p, x, y, text, stroke, clamp_top=None, clamp_right=None):
        """Outline-only status pill anchored at (x, y).

        Only the stroke carries the status color — dark translucent fill keeps
        the target visible underneath. Drawn above the box, flipped below it
        when there is no room, and shifted left to stay inside the image.
        Returns the pill rect in widget coords.
        """
        f = QFont("Segoe UI", 7)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(text) + 14
        th = 16
        if clamp_top is not None and y - th - 2 < clamp_top:
            ry = y + 4
        else:
            ry = y - th - 4
        rx = int(x)
        if clamp_right is not None and rx + tw > clamp_right:
            rx = int(max(clamp_right - tw, 0))
        r = QRect(rx, int(ry), int(tw), th)
        p.setPen(QPen(stroke, 1))
        p.setBrush(QColor(0, 0, 0, 150))
        p.drawRoundedRect(r, 5, 5)
        p.setPen(QColor(255, 255, 255))
        p.setFont(f)
        p.drawText(r, Qt.AlignCenter, text)
        return r

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # pure black canvas when idle — overlays only after START
        p.fillRect(self.rect(), QColor(0, 0, 0))
        if self._rgb is None:
            return
        # fit image into black rect (keep aspect)
        avail = self.rect()
        scale = min(avail.width() / self._w, avail.height() / self._h)
        disp_w = max(1, int(self._w * scale))
        disp_h = max(1, int(self._h * scale))
        ox = avail.x() + (avail.width() - disp_w) // 2
        oy = avail.y() + (avail.height() - disp_h) // 2
        qimg = QImage(self._rgb.data, self._w, self._h, self._w * 3, QImage.Format_RGB888)
        pix = QPixmap.fromImage(qimg).scaled(disp_w, disp_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        p.drawPixmap(ox, oy, pix)

        # ---- system status banner (top-left): global track state only ----
        # The label/color come from DisplayTracker (single source of truth).
        _disp = getattr(self, "_display", None)
        if not isinstance(_disp, DisplayState):
            _disp = DisplayState(status=DisplayStatus.SCANNING,
                                 show_no_target=True)
        _label, _hex, _chip = _disp.label, _disp.color_hex, _disp.show_no_target
        try:
            _f = QFont("Segoe UI", 8)
            _f.setWeight(QFont.Bold)
            p.setFont(_f)
            _fm = p.fontMetrics()
            _txt = f"\u25cf  {_label}"
            _tw = _fm.horizontalAdvance(_txt) + 18
            _th = 20
            _r = QRect(ox + 8, oy + 8, int(_tw), _th)
            p.setPen(QPen(QColor(_hex), 1))
            p.setBrush(QColor(0, 0, 0, 150))
            p.drawRoundedRect(_r, 8, 8)
            p.setPen(QColor(255, 255, 255))
            p.setFont(_f)
            p.drawText(_r.adjusted(4, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, _txt)
            if _chip:
                _f2 = QFont("Segoe UI", 7)
                _f2.setWeight(QFont.DemiBold)
                p.setFont(_f2)
                _fm2 = p.fontMetrics()
                _t2 = "NO TARGET"
                _tw2 = _fm2.horizontalAdvance(_t2) + 16
                _r2 = QRect(ox + 8, oy + 8 + _th + 6, int(_tw2), 16)
                p.setPen(QPen(QColor("#9CA3AF"), 1))
                p.setBrush(QColor(0, 0, 0, 150))
                p.drawRoundedRect(_r2, 6, 6)
                p.setPen(QColor(255, 255, 255))
                p.setFont(_f2)
                p.drawText(_r2, Qt.AlignCenter, _t2)
        except Exception:
            pass

        # overlays mapped to widget coords
        def to_widget(ix, iy):
            return ox + int(ix * scale), oy + int(iy * scale)

        # centre offset (calibration)
        if self._centre_offset is not None:
            try:
                dx, dy = self._centre_offset
                ccx, ccy = int(self._w // 2 + float(dx)), int(self._h // 2 + float(dy))
            except Exception:
                ccx, ccy = self._w // 2, self._h // 2
        else:
            ccx, ccy = self._w // 2, self._h // 2

        # reticle: white square + circle at boresight (wireframe look)
        rcx, rcy = to_widget(ccx, ccy)
        p.setPen(QPen(QColor(255, 255, 255), 1))
        s = max(8, int(28 * scale))
        p.drawRect(rcx - s, rcy - int(s * 0.8), s * 2, int(s * 1.6))
        p.drawEllipse(rcx - 6, rcy - 6, 12, 12)
        # crosshair ticks through boresight
        p.drawLine(rcx - s - 10, rcy, rcx - s + 6, rcy)
        p.drawLine(rcx + s - 6, rcy, rcx + s + 10, rcy)
        p.drawLine(rcx, rcy - int(s * 0.8) - 10, rcx, rcy - int(s * 0.8) + 6)
        p.drawLine(rcx, rcy + int(s * 0.8) - 6, rcx, rcy + int(s * 0.8) + 10)

        # target annotation: identity + per-target state + real measurements.
        # TGT-01 labels the tracked object, the status mirrors the banner,
        # DET is the detector confidence of this frame, OFFSET is the live
        # boresight pixel offset. Nothing here is synthesized.
        det = self._detection
        det_xy = None
        tele = getattr(self, "_telemetry", None)
        _tid = (tele.track_label if tele is not None else "TGT-01") or "TGT-01"

        def est_pos_for_edge():
            ex0, ey0 = self._estimate.pos_px
            return ox + int(float(ex0) * scale), oy + int(float(ey0) * scale)
        if det is not None and getattr(det, "valid", False) and getattr(det, "centroid_px", None):
            try:
                x, y = det.centroid_px
                wx, wy = to_widget(x, y)
                det_xy = (wx, wy)
                # error vector: boresight -> target (centering error, live)
                p.setPen(QPen(QColor(255, 255, 255, 200), 1))
                p.drawLine(rcx, rcy, wx, wy)
                # centroid rings
                p.setPen(QPen(QColor(255, 255, 255), 1))
                p.drawEllipse(wx - 6, wy - 6, 12, 12)
                p.drawEllipse(wx - 10, wy - 10, 20, 20)
                # cross
                p.drawLine(wx - 8, wy, wx + 8, wy)
                p.drawLine(wx, wy - 8, wx, wy + 8)
                try:
                    import math
                    _off = math.hypot(x - ccx, y - ccy)
                except Exception:
                    _off = None
                conf_pct = f"{float(getattr(det, 'confidence', 0.0)) * 100:.0f}%"
                tag = f"{_tid}  \u00b7  {_label}"
                tag_bg = QColor(_hex)
                box_col = QColor(_hex)
                parts = [f"DET {conf_pct}"]
                parts.append(f"OFFSET {_off:.0f} px" if _off is not None else "OFFSET \u2014")
                sub = "  \u00b7  ".join(parts)
                if getattr(det, "bbox", None):
                    bx, by, bw, bh = det.bbox
                    x0, y0 = to_widget(bx, by)
                    x1, y1 = to_widget(bx + bw, by + bh)
                    p.setPen(QPen(box_col, 1))
                    p.drawRect(QRect(x0, y0, x1 - x0, y1 - y0))
                    r1 = self._draw_tag(p, x0, y0, tag, tag_bg, clamp_top=oy,
                                        clamp_right=ox + disp_w - 4)
                    self._draw_tag(p, r1.x(), r1.y() + r1.height() + 18, sub,
                                   QColor("#9CA3AF"), clamp_top=oy,
                                   clamp_right=ox + disp_w - 4)
                else:
                    r1 = self._draw_tag(p, wx + 12, wy, tag, tag_bg, clamp_top=oy,
                                        clamp_right=ox + disp_w - 4)
                    self._draw_tag(p, r1.x(), r1.y() + r1.height() + 18, sub,
                                   QColor("#9CA3AF"), clamp_top=oy,
                                   clamp_right=ox + disp_w - 4)
            except Exception:
                pass
        elif (tele is not None and tele.predicted and tele.pred_fresh
                and _disp.status == DisplayStatus.OFF_SCREEN):
            # tracked target outside the frame: edge arrow toward the live
            # IMM prediction + identity chip (prediction, not a detection)
            try:
                ex, ey = est_pos_for_edge()
                m = 14
                ex_c = min(max(ex, ox + m), ox + disp_w - m)
                ey_c = min(max(ey, oy + m), oy + disp_h - m)
                import math
                ang = math.atan2(ey - ey_c, ex - ex_c)
                p.setPen(QPen(QColor(_hex), 1))
                p.drawEllipse(ex_c - 7, ey_c - 7, 14, 14)
                p.drawLine(ex_c, ey_c,
                           int(ex_c + 16 * math.cos(ang)), int(ey_c + 16 * math.sin(ang)))
                self._draw_tag(p, ex_c + 12, ey_c, f"{_tid}  \u00b7  OFF-SCREEN",
                               QColor(_hex), clamp_top=oy,
                               clamp_right=ox + disp_w - 4)
            except Exception:
                pass

        # rejected blobs: dashed red boxes with REJECTED tags (failed area/shape gates)
        try:
            rej = list(getattr(det, "rejected", []) or [])[:4]
        except Exception:
            rej = []
        for rj in rej:
            try:
                bx, by, bw, bh = int(rj[0]), int(rj[1]), int(rj[2]), int(rj[3])
                reason = str(rj[4]) if len(rj) > 4 else ""
                x0, y0 = to_widget(bx, by)
                x1, y1 = to_widget(bx + bw, by + bh)
                p.setPen(QPen(QColor(230, 60, 60), 1, Qt.DashLine))
                p.drawRect(QRect(x0, y0, max(3, x1 - x0), max(3, y1 - y0)))
                lbl = f"REJECTED {reason}".strip()
                self._draw_tag(p, x0, y0, lbl, QColor(190, 40, 40), clamp_top=oy,
                               clamp_right=ox + disp_w - 4)
            except Exception:
                continue

        # estimate trail + marker (shows fused motion dynamics)
        # trail first so marker draws on top
        if len(self._est_trail) > 1:
            prev = None
            n = len(self._est_trail)
            for i, pt in enumerate(self._est_trail):
                wpt = to_widget(pt[0], pt[1])
                if prev is not None:
                    alpha = int(60 + 140 * (i / n))
                    p.setPen(QPen(QColor(0, 255, 120, alpha), 1))
                    p.drawLine(prev[0], prev[1], wpt[0], wpt[1])
                prev = wpt
        est = self._estimate
        _det_now_valid = bool(det is not None and getattr(det, "valid", False)
                              and getattr(det, "centroid_px", None))
        if est is not None and getattr(est, "pos_px", None):
            try:
                ex, ey = to_widget(est.pos_px[0], est.pos_px[1])
                _coasting = (not _det_now_valid and tele is not None
                             and tele.predicted and tele.pred_fresh)
                if _det_now_valid or _coasting:
                    # white strokes only; coasting prediction is hollow/dashed
                    # and explicitly tagged so it can't be mistaken for a fix
                    if _coasting:
                        p.setPen(QPen(QColor(255, 255, 255), 1, Qt.DashLine))
                    else:
                        p.setPen(QPen(QColor(255, 255, 255), 1))
                    p.drawEllipse(ex - 7, ey - 7, 14, 14)
                    if _coasting:
                        self._draw_tag(p, ex + 10, ey - 10, "PREDICTED",
                                       QColor("#9CA3AF"), clamp_top=oy,
                                       clamp_right=ox + disp_w - 4)
                # velocity arrow (direction of motion, from filter velocity)
                # drawn only while a live marker is shown (fix or fresh prediction)
                try:
                    vx, vy = est.vel_angle  # deg/s
                    px_per_deg = (self._w / 4.0)
                    dx = float(vx) * px_per_deg * 0.25
                    dy = float(-vy) * px_per_deg * 0.25
                    if (_det_now_valid or _coasting) and (abs(dx) > 3 or abs(dy) > 3):
                        p.setPen(QPen(QColor(255, 255, 255), 1))
                        p.drawLine(ex, ey, int(ex + dx), int(ey + dy))
                        # arrowhead
                        import math
                        ang = math.atan2(dy, dx)
                        for da in (2.6, -2.6):
                            ax = int(ex + dx - 7 * math.cos(ang + da))
                            ay = int(ey + dy - 7 * math.sin(ang + da))
                            p.drawLine(int(ex + dx), int(ey + dy), ax, ay)
                except Exception:
                    pass
            except Exception:
                pass


class WorldView(QWidget):
    """World FOV — pure black viewport with white camera footprint (Main Window.pdf)."""

    def __init__(self, world_size=(2000, 2000), parent=None):
        super().__init__(parent)
        self.world_w, self.world_h = world_size
        self.camera_bounds = None
        self.camera_center = (world_size[0] / 2, world_size[1] / 2)
        self.world_pos = None
        self.trail = []
        self.all_world_pos = []
        self.target_trails = {}  # idx -> [world (x, y)]
        self._thumb = None  # downscaled full-scene RGB for background
        self.cam_res = (640, 480)
        self.setMinimumSize(400, 340)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: black; border: none;")

    def set_world_image(self, world_img, all_positions=None):
        """Full-scene background (environment + ALL beacons) + per-target trails."""
        try:
            import cv2
            import numpy as np
            h, w = world_img.shape[:2]
            long_edge = 480
            s = min(1.0, long_edge / max(w, h))
            if s < 1.0:
                thumb = cv2.resize(world_img, (max(1, int(w * s)), max(1, int(h * s))),
                                   interpolation=cv2.INTER_AREA)
            else:
                thumb = world_img
            if len(thumb.shape) == 2:
                rgb = cv2.cvtColor(thumb, cv2.COLOR_GRAY2RGB)
            else:
                rgb = cv2.cvtColor(thumb, cv2.COLOR_BGR2RGB)
            self._thumb = np.ascontiguousarray(rgb)
        except Exception:
            self._thumb = None
        try:
            positions = list(all_positions) if all_positions is not None else []
        except Exception:
            positions = []
        self.all_world_pos = [(float(p[0]), float(p[1])) for p in positions]
        for idx, pt in enumerate(self.all_world_pos):
            tr = self.target_trails.setdefault(idx, [])
            if not tr or tr[-1] != pt:
                tr.append(pt)
                if len(tr) > 220:
                    tr.pop(0)
        # primary mirror for backward compat
        if self.all_world_pos:
            self.trail = self.target_trails.get(0, self.trail)
        self.update()

    def update_state(self, camera, world_pos, trail=None):
        if camera is not None:
            try:
                self.camera_bounds = camera.get_viewport_bounds()
                self.camera_center = tuple(camera.center_world)
                # footprint size ~ camera resolution aspect; keep label res from bounds
                try:
                    l, t, r, b = self.camera_bounds
                    self.cam_res = (int(r - l), int(b - t))
                except Exception:
                    pass
            except Exception:
                pass
        if world_pos is not None:
            self.world_pos = world_pos
            self.trail.append(tuple(world_pos))
            if len(self.trail) > 220:
                self.trail.pop(0)
        self.update()

    def clear(self):
        self.camera_bounds = None
        self.world_pos = None
        self.trail.clear()
        self.all_world_pos = []
        self.target_trails.clear()
        self._thumb = None
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(0, 0, 0))
        if self.camera_bounds is None:
            return

        pad = 8
        avail_w = self.width() - pad * 2
        avail_h = self.height() - pad * 2
        scale = min(avail_w / self.world_w, avail_h / self.world_h)
        ox = pad + (avail_w - self.world_w * scale) / 2
        oy = pad + (avail_h - self.world_h * scale) / 2
        world_rect = QRect(int(ox), int(oy),
                           max(1, int(self.world_w * scale)), max(1, int(self.world_h * scale)))

        # full scene: environment background + stars/gradient + all beacons
        if self._thumb is not None:
            try:
                th, tw = self._thumb.shape[:2]
                qimg = QImage(self._thumb.data, tw, th, tw * 3, QImage.Format_RGB888)
                p.drawPixmap(world_rect, QPixmap.fromImage(qimg))
            except Exception:
                pass
        else:
            p.setPen(QPen(QColor(60, 60, 60), 1))
            p.setBrush(QColor(10, 10, 10))
            p.drawRect(world_rect)

        # trails for EVERY target (primary amber, others white)
        for idx in sorted(self.target_trails.keys()):
            tr = self.target_trails[idx]
            if len(tr) < 2:
                continue
            col = QColor(255, 180, 40, 170) if idx == 0 else QColor(255, 255, 255, 120)
            p.setPen(QPen(col, 2 if idx == 0 else 1))
            prev = None
            for pt in tr:
                x = ox + pt[0] * scale
                y = oy + pt[1] * scale
                if prev is not None:
                    p.drawLine(int(prev[0]), int(prev[1]), int(x), int(y))
                prev = (x, y)

        # camera footprint — white outline (exact design)
        try:
            l, t, r, b = self.camera_bounds
            fx = ox + l * scale
            fy = oy + t * scale
            fw = (r - l) * scale
            fh = (b - t) * scale
            p.setPen(QPen(QColor(255, 255, 255), 1))
            p.drawRect(int(fx), int(fy), int(fw), int(fh))
            p.setFont(QFont("Segoe UI", 7))
            p.setPen(QColor(255, 255, 255))
            rw, rh = self.cam_res
            # keep label inside top edge like wireframe
            p.drawText(int(fx), int(fy) - 16, int(fw), 14, Qt.AlignLeft, f"Camera FOV ({rw}, {rh})")
        except Exception:
            pass

        # ALL beacons with index tags (T1 primary, T2..Tn)
        positions = self.all_world_pos or ([self.world_pos] if self.world_pos is not None else [])
        for idx, pt in enumerate(positions):
            try:
                tx = ox + pt[0] * scale
                ty = oy + pt[1] * scale
                if idx == 0:
                    p.setPen(QPen(QColor(255, 180, 40), 1))
                    p.setBrush(QColor(255, 170, 20))
                    ix, iy = int(tx), int(ty)
                    p.save()
                    p.translate(ix, iy)
                    p.rotate(45)
                    p.drawRect(-5, -5, 10, 10)
                    p.restore()
                else:
                    p.setPen(QPen(QColor(255, 255, 255), 1))
                    p.setBrush(QColor(255, 255, 255))
                    p.drawEllipse(int(tx) - 3, int(ty) - 3, 6, 6)
                p.setFont(QFont("Segoe UI", 7))
                p.setPen(QColor(255, 255, 255))
                p.drawText(int(tx) + 8, int(ty) - 8, 60, 14, Qt.AlignLeft,
                           f"TGT-{idx + 1:02d}")
            except Exception:
                continue
