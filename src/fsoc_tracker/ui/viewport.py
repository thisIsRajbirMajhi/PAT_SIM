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
        self._target_size = 10    # beacon side length in image px (fallback box)
        self.show_grid = False
        self.show_trails = False    
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: black; border: none;")

    def set_frame(self, frame_gray, detection=None, estimate=None, world_camera=None,
                  show_overlays=True, meta=None, centre_offset=None,
                  display=None, telemetry=None, display_status=None,
                  target_size_px=None):
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
        if target_size_px is not None:
            try:
                self._target_size = max(4, int(target_size_px))
            except Exception:
                pass
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
        # base fill (only visible when idle — live frames cover it fully)
        p.fillRect(self.rect(), QColor(0, 0, 0))
        if self._rgb is None:
            return
        # fill viewport completely (cover, center-cropped): no black bars.
        # scale = max() so every widget pixel shows image content; QPainter
        # clips the overflow beyond the widget edges automatically.
        avail = self.rect()
        scale = max(avail.width() / self._w, avail.height() / self._h)
        disp_w = max(1, int(self._w * scale))
        disp_h = max(1, int(self._h * scale))
        ox = avail.x() + (avail.width() - disp_w) // 2
        oy = avail.y() + (avail.height() - disp_h) // 2
        vis_left = avail.x()
        vis_top = avail.y()
        vis_right = avail.x() + avail.width()
        vis_bottom = avail.y() + avail.height()
        qimg = QImage(self._rgb.data, self._w, self._h, self._w * 3, QImage.Format_RGB888)
        # Render at native pixels when possible: smooth only when downscaling,
        # fast (nearest) when upscaling so actual sensor resolution stays crisp.
        _mode = Qt.SmoothTransformation if scale < 1.0 else Qt.FastTransformation
        pix = QPixmap.fromImage(qimg).scaled(disp_w, disp_h, Qt.IgnoreAspectRatio, _mode)
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
            _r = QRect(vis_left + 8, vis_top + 8, int(_tw), _th)
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
                _r2 = QRect(vis_left + 8, vis_top + 8 + _th + 6, int(_tw2), 16)
                p.setPen(QPen(QColor("#9CA3AF"), 1))
                p.setBrush(QColor(0, 0, 0, 150))
                p.drawRoundedRect(_r2, 6, 6)
                p.setPen(QColor(255, 255, 255))
                p.setFont(_f2)
                p.drawText(_r2, Qt.AlignCenter, _t2)
        except Exception:
            pass

        # ---- overlay palette: everything keyed off the live state color ----
        # Single accent = state color; informational helpers stay neutral gray.
        try:
            state_col = QColor(_hex)
        except Exception:
            state_col = QColor("#9AA4B2")
        dim_col = QColor("#9CA3AF")

        # overlays mapped to widget coords
        def to_widget(ix, iy):
            return ox + int(ix * scale), oy + int(iy * scale)

        def _in_frame(ix, iy):
            return 0 <= ix < self._w and 0 <= iy < self._h

        def _fallback_box(cx, cy):
            # config-sized box centered on (cx, cy) in image coords, so a
            # bounding box exists even with no detector bbox (coasting, etc.)
            _s = max(8, int(self._target_size) + 4)
            return (int(cx - _s / 2), int(cy - _s / 2), _s, _s)

        # centre offset (calibration)
        if self._centre_offset is not None:
            try:
                dx, dy = self._centre_offset
                ccx, ccy = int(self._w // 2 + float(dx)), int(self._h // 2 + float(dy))
            except Exception:
                ccx, ccy = self._w // 2, self._h // 2
        else:
            ccx, ccy = self._w // 2, self._h // 2

        # boresight reticle: minimal crosshair + center dot in state color
        rcx, rcy = to_widget(ccx, ccy)
        p.setPen(QPen(state_col, 1))
        _gap, _arm = 10, 14
        p.drawLine(rcx - _gap - _arm, rcy, rcx - _gap, rcy)
        p.drawLine(rcx + _gap, rcy, rcx + _gap + _arm, rcy)
        p.drawLine(rcx, rcy - _gap - _arm, rcx, rcy - _gap)
        p.drawLine(rcx, rcy + _gap, rcx, rcy + _gap + _arm)
        p.setBrush(state_col)
        p.setPen(Qt.NoPen)
        p.drawEllipse(rcx - 2, rcy - 2, 4, 4)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(state_col, 1))

        # target annotation: one state-colored marker + one info tag.
        # Tag carries identity, detector confidence and live boresight offset
        # — the three facts that matter for this frame. Nothing synthesized.
        det = self._detection
        det_xy = None
        tele = getattr(self, "_telemetry", None)
        _tid = (tele.track_label if tele is not None else "TGT-01") or "TGT-01"

        def est_pos_for_edge():
            ex0, ey0 = self._estimate.pos_px
            return ox + int(float(ex0) * scale), oy + int(float(ey0) * scale)

        def _info_tag():
            try:
                import math
                _off = math.hypot(x - ccx, y - ccy)
            except Exception:
                _off = None
            conf_pct = f"{float(getattr(det, 'confidence', 0.0)) * 100:.0f}%"
            _off_txt = f"{_off:.0f}px" if _off is not None else "—"
            return f"{_tid}  ·  DET {conf_pct}  ·  OFF {_off_txt}"

        if det is not None and getattr(det, "valid", False) and getattr(det, "centroid_px", None):
            try:
                x, y = det.centroid_px
                wx, wy = to_widget(x, y)
                det_xy = (wx, wy)
                # centering-error vector: boresight -> target (live)
                _err = QColor(state_col)
                _err.setAlpha(170)
                p.setPen(QPen(_err, 1))
                p.drawLine(rcx, rcy, wx, wy)
                # single state-colored ring + cross (outline only)
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(state_col, 2))
                p.drawEllipse(wx - 9, wy - 9, 18, 18)
                p.setPen(QPen(state_col, 1))
                p.drawLine(wx - 13, wy, wx + 13, wy)
                p.drawLine(wx, wy - 13, wx, wy + 13)
                tag = _info_tag()
                _bbox = getattr(det, "bbox", None)
                if _bbox is None and _in_frame(x, y):
                    # valid centroid but no component box: config-sized fallback
                    _bbox = _fallback_box(x, y)
                if _bbox is not None:
                    bx, by, bw, bh = _bbox
                    x0, y0 = to_widget(bx, by)
                    x1, y1 = to_widget(bx + bw, by + bh)
                    p.setBrush(Qt.NoBrush)
                    p.setPen(QPen(state_col, 2))
                    p.drawRect(QRect(x0, y0, x1 - x0, y1 - y0))
                    self._draw_tag(p, x0, y0, tag, state_col, clamp_top=vis_top,
                                   clamp_right=vis_right - 4)
                else:
                    self._draw_tag(p, wx + 14, wy, tag, state_col, clamp_top=vis_top,
                                   clamp_right=vis_right - 4)
            except Exception:
                pass
        elif (tele is not None and tele.predicted and tele.pred_fresh
                and _disp.status == DisplayStatus.OFF_SCREEN):
            # tracked target outside the frame: edge marker toward the live
            # IMM prediction + identity chip (prediction, not a detection)
            try:
                ex, ey = est_pos_for_edge()
                m = 14
                ex_c = min(max(ex, vis_left + m), vis_right - m)
                ey_c = min(max(ey, vis_top + m), vis_bottom - m)
                import math
                ang = math.atan2(ey - ey_c, ex - ex_c)
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(state_col, 2))
                p.drawEllipse(ex_c - 7, ey_c - 7, 14, 14)
                p.drawLine(ex_c, ey_c,
                           int(ex_c + 18 * math.cos(ang)), int(ey_c + 18 * math.sin(ang)))
                self._draw_tag(p, ex_c + 12, ey_c, f"{_tid}  ·  OFF-SCREEN",
                               state_col, clamp_top=vis_top,
                               clamp_right=vis_right - 4)
            except Exception:
                pass

        # rejected blobs: subtle dashed outline (failed area/shape gates)
        try:
            rej = list(getattr(det, "rejected", []) or [])[:3]
        except Exception:
            rej = []
        for rj in rej:
            try:
                bx, by, bw, bh = int(rj[0]), int(rj[1]), int(rj[2]), int(rj[3])
                reason = str(rj[4]) if len(rj) > 4 else ""
                x0, y0 = to_widget(bx, by)
                x1, y1 = to_widget(bx + bw, by + bh)
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(QColor(230, 60, 60), 1, Qt.DashLine))
                p.drawRect(QRect(x0, y0, max(3, x1 - x0), max(3, y1 - y0)))
                if reason:
                    self._draw_tag(p, x0, y0, f"REJ {reason}", QColor(190, 40, 40),
                                   clamp_top=vis_top, clamp_right=vis_right - 4)
            except Exception:
                continue

        # motion trail in state color (fades toward the past) + prediction marker.
        # While a live detection exists the target ring above is the marker,
        # so the estimate is only drawn separately when coasting on prediction.
        if self.show_trails and len(self._est_trail) > 1:
            prev = None
            n = len(self._est_trail)
            for i, pt in enumerate(self._est_trail):
                wpt = to_widget(pt[0], pt[1])
                if prev is not None:
                    alpha = int(60 + 140 * (i / n))
                    _tc = QColor(state_col)
                    _tc.setAlpha(alpha)
                    p.setPen(QPen(_tc, 2))
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
                if _coasting:
                    # dashed config-sized box at the predicted position,
                    # explicitly tagged so it can't be mistaken for a fix
                    try:
                        _px, _py = est.pos_px
                        if _in_frame(_px, _py):
                            _fx, _fy, _fw, _fh = _fallback_box(_px, _py)
                            _fx0, _fy0 = to_widget(_fx, _fy)
                            _fx1, _fy1 = to_widget(_fx + _fw, _fy + _fh)
                            p.setBrush(Qt.NoBrush)
                            p.setPen(QPen(state_col, 2, Qt.DashLine))
                            p.drawRect(QRect(_fx0, _fy0, _fx1 - _fx0, _fy1 - _fy0))
                    except Exception:
                        pass
                    self._draw_tag(p, ex + 12, ey - 12, "PREDICTED",
                                   dim_col, clamp_top=vis_top,
                                   clamp_right=vis_right - 4)
                # velocity arrow (filter motion direction) in state color
                try:
                    vx, vy = est.vel_angle  # deg/s
                    px_per_deg = (self._w / 4.0)
                    dx = float(vx) * px_per_deg * 0.25 * scale
                    dy = float(-vy) * px_per_deg * 0.25 * scale
                    if (_det_now_valid or _coasting) and (abs(dx) > 3 or abs(dy) > 3):
                        p.setPen(QPen(state_col, 1))
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
        self.state_hex = "#FFFFFF"  # live state color (set each tick via set_state_color)
        self.show_trails = False
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: black; border: none;")

    def set_world_image(self, world_img, all_positions=None):
        """Full-scene background (environment + ALL beacons) + per-target trails.

        Keeps native resolution (long edge up to 1200px) so the World FOV
        renders the actual scene detail instead of a coarse thumbnail.
        """
        try:
            import cv2
            import numpy as np
            if world_img is None:
                self._thumb = None
            else:
                h, w = world_img.shape[:2]
                long_edge = 1200
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

    def set_state_color(self, color_hex):
        """Live track-state color driving footprint / primary trail / marker."""
        try:
            if color_hex:
                QColor(color_hex)  # validate
                self.state_hex = str(color_hex)
        except Exception:
            pass

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
        self.state_hex = "#FFFFFF"
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(0, 0, 0))
        if self.camera_bounds is None:
            return

        # fill viewport completely (cover, center-cropped): no black bars.
        avail_w = self.width()
        avail_h = self.height()
        scale = max(avail_w / self.world_w, avail_h / self.world_h)
        ox = (avail_w - self.world_w * scale) / 2
        oy = (avail_h - self.world_h * scale) / 2
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
            p.fillRect(self.rect(), QColor(10, 10, 10))

        # live state color
        try:
            state_col = QColor(self.state_hex)
        except Exception:
            state_col = QColor(255, 255, 255)

        # trails: primary in live state color, others dim white
        if self.show_trails:
            for idx in sorted(self.target_trails.keys()):
                tr = self.target_trails[idx]
                if len(tr) < 2:
                    continue
                if idx == 0:
                    col = QColor(state_col)
                    col.setAlpha(180)
                    p.setPen(QPen(col, 2))
                else:
                    p.setPen(QPen(QColor(255, 255, 255, 110), 1))
                prev = None
                for pt in tr:
                    x = ox + pt[0] * scale
                    y = oy + pt[1] * scale
                    if prev is not None:
                        p.drawLine(int(prev[0]), int(prev[1]), int(x), int(y))
                    prev = (x, y)

        # camera footprint in live state color
        try:
            l, t, r, b = self.camera_bounds
            fx = ox + l * scale
            fy = oy + t * scale
            fw = (r - l) * scale
            fh = (b - t) * scale
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(state_col, 2))
            p.drawRect(int(fx), int(fy), int(fw), int(fh))
            p.setFont(QFont("Segoe UI", 7))
            p.setPen(state_col)
            rw, rh = self.cam_res
            # keep label visible when the footprint is cropped at the top
            _ly = max(0, int(fy) - 16)
            p.drawText(int(fx), _ly, int(fw), 14, Qt.AlignLeft, f"Camera FOV ({rw}, {rh})")
        except Exception:
            pass

        # beacons: primary diamond in state color, others small gray dots
        positions = self.all_world_pos or ([self.world_pos] if self.world_pos is not None else [])
        for idx, pt in enumerate(positions):
            try:
                tx = ox + pt[0] * scale
                ty = oy + pt[1] * scale
                if idx == 0:
                    p.setPen(QPen(state_col, 2))
                    p.setBrush(state_col)
                    ix, iy = int(tx), int(ty)
                    p.save()
                    p.translate(ix, iy)
                    p.rotate(45)
                    p.drawRect(-5, -5, 10, 10)
                    p.restore()
                else:
                    p.setPen(QPen(QColor(160, 160, 160), 1))
                    p.setBrush(QColor(160, 160, 160))
                    p.drawEllipse(int(tx) - 3, int(ty) - 3, 6, 6)
                p.setFont(QFont("Segoe UI", 7))
                p.setPen(state_col if idx == 0 else QColor(160, 160, 160))
                p.drawText(int(tx) + 8, int(ty) - 8, 60, 14, Qt.AlignLeft,
                           f"TGT-{idx + 1:02d}")
            except Exception:
                continue
