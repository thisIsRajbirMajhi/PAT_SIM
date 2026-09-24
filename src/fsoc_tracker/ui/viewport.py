import cv2
import numpy as np
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QRect, QPoint
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont, QBrush
from .theme import COLORS

# Convert BGR (cv2) tuple to QColor via RGB
def bgr_to_qcolor(bgr):
    return QColor(bgr[2], bgr[1], bgr[0])

class CameraView(QWidget):
    """
    Light-chrome camera view with dense but disciplined overlays:
    - Hairline header with live stats (FPS/res/FOV)
    - Image with reticle, detection bbox+label, estimate marker+velocity, error vector+distance
    - Corner HUD: TL confidence, TR state, BL coordinates, BR scale bar
    - Optional grid (8x6) and recent estimate trail
    """
    def __init__(self, title="CAMERA FOV", parent=None):
        super().__init__(parent)
        self.title = title
        self._rgb = None
        self._w = 640
        self._h = 480
        self._detection = None
        self._estimate = None
        self._est_trail = []  # recent estimate positions
        self._meta = {}  # fps, fov, res, etc.
        self.show_reticle = True
        self.show_grid = False
        self.setMinimumSize(560, 420)
        from PyQt5.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {COLORS['surface']}; border: 1px solid {COLORS['border']}; border-radius: 8px;")

    def set_frame(self, frame_gray, detection=None, estimate=None, world_camera=None, show_overlays=True, meta=None):
        if frame_gray is None:
            return
        h, w = frame_gray.shape
        self._w, self._h = w, h
        self._detection = detection
        self._estimate = estimate
        self._meta = meta or {}
        # keep trail
        if estimate and estimate.pos_px:
            self._est_trail.append(tuple(estimate.pos_px))
            if len(self._est_trail) > 32:
                self._est_trail.pop(0)
        else:
            # fade trail if no estimate
            if len(self._est_trail) > 0 and (estimate is None or estimate.tracking_state.value in ("SEARCHING","FAILED")):
                # slowly decay
                pass

        rgb = cv2.cvtColor(frame_gray, cv2.COLOR_GRAY2RGB)
        overlay = rgb.copy()

        if show_overlays:
            cx, cy = w // 2, h // 2

            # --- subtle grid (optional) ---
            if self.show_grid:
                gh, gw = 6, 8
                for i in range(1, gw):
                    x = int(w * i / gw)
                    cv2.line(overlay, (x, 0), (x, h), (210, 215, 225), 1, cv2.LINE_AA)
                for j in range(1, gh):
                    y = int(h * j / gh)
                    cv2.line(overlay, (0, y), (w, y), (210, 215, 225), 1, cv2.LINE_AA)

            # --- reticle: precise crosshair with tick marks, not neon circles ---
            if self.show_reticle:
                # main cross
                cv2.line(overlay, (cx - 18, cy), (cx - 6, cy), (37, 99, 235), 1, cv2.LINE_AA)
                cv2.line(overlay, (cx + 6, cy), (cx + 18, cy), (37, 99, 235), 1, cv2.LINE_AA)
                cv2.line(overlay, (cx, cy - 18), (cx, cy - 6), (37, 99, 235), 1, cv2.LINE_AA)
                cv2.line(overlay, (cx, cy + 6), (cx, cy + 18), (37, 99, 235), 1, cv2.LINE_AA)
                # corner brackets (frame)
                r = 14
                cv2.rectangle(overlay, (cx - r, cy - r), (cx + r, cy + r), (37, 99, 235), 1, cv2.LINE_AA)
                # ticks every 60px
                for d in (-60, -120, 60, 120):
                    cv2.line(overlay, (cx + d, cy - 4), (cx + d, cy + 4), (148, 163, 184), 1, cv2.LINE_AA)
                    cv2.line(overlay, (cx - 4, cy + d), (cx + 4, cy + d), (148, 163, 184), 1, cv2.LINE_AA)

            # --- detection: bbox + cross + label ---
            if detection and detection.valid and detection.centroid_px:
                x, y = int(round(detection.centroid_px[0])), int(round(detection.centroid_px[1]))
                # bbox
                if detection.bbox:
                    bx, by, bw, bh = detection.bbox
                    cv2.rectangle(overlay, (bx, by), (bx + bw, by + bh), (180, 83, 9), 1, cv2.LINE_AA)  # amber-700
                    # bbox corner ticks
                    tl = 6
                    cv2.line(overlay, (bx, by), (bx + tl, by), (180, 83, 9), 2)
                    cv2.line(overlay, (bx, by), (bx, by + tl), (180, 83, 9), 2)
                # centroid
                cv2.drawMarker(overlay, (x, y), (180, 83, 9), markerType=cv2.MARKER_CROSS, markerSize=12, thickness=1, line_type=cv2.LINE_AA)
                cv2.circle(overlay, (x, y), 5, (180, 83, 9), 1, cv2.LINE_AA)
                cv2.circle(overlay, (x, y), 9, (180, 83, 9), 1, cv2.LINE_AA)
                # error vector from center
                cv2.line(overlay, (cx, cy), (x, y), (180, 83, 9), 1, cv2.LINE_AA)
                # distance label near midpoint
                mx, my = (cx + x) // 2, (cy + y) // 2
                dist = np.hypot(x - cx, y - cy)
                cv2.putText(overlay, f"{dist:.0f}px", (mx + 6, my - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (180, 83, 9), 1, cv2.LINE_AA)

            # --- estimate: distinct marker + velocity arrow + trail ---
            if estimate and estimate.pos_px:
                ex, ey = int(round(estimate.pos_px[0])), int(round(estimate.pos_px[1]))
                state = estimate.tracking_state.value
                if state == "LOCKED":
                    col = (21, 128, 61)  # green-700 BGR
                    marker = cv2.MARKER_TILTED_CROSS
                elif state in ("TEMP_LOST", "REACQUIRING"):
                    col = (184, 28, 28)  # red
                    marker = cv2.MARKER_DIAMOND
                else:
                    col = (100, 116, 139)  # slate-500
                    marker = cv2.MARKER_CROSS
                # trail
                if len(self._est_trail) > 1:
                    for i in range(1, len(self._est_trail)):
                        a = i / len(self._est_trail)
                        # fade
                        thickness = 1
                        pt1 = tuple(map(int, self._est_trail[i - 1]))
                        pt2 = tuple(map(int, self._est_trail[i]))
                        # desaturated green
                        b, g, r = col
                        # blend with white by alpha
                        cv2.line(overlay, pt1, pt2, (int(b + (255 - b) * (1 - a) * 0.7), int(g + (255 - g) * (1 - a) * 0.7), int(r + (255 - r) * (1 - a) * 0.7)), 1, cv2.LINE_AA)
                cv2.drawMarker(overlay, (ex, ey), col, markerType=marker, markerSize=14, thickness=1, line_type=cv2.LINE_AA)
                cv2.circle(overlay, (ex, ey), 7, col, 1, cv2.LINE_AA)
                # velocity vector (from estimate.vel_angle if available)
                try:
                    vx, vy = estimate.vel_angle  # deg/s
                    # scale to pixels: 1 deg ~ W/FOV = 160 px/deg
                    scale = (self._w / 4.0) * 0.18  # tuned
                    dx = int(vx * scale)
                    dy = int(-vy * scale)  # tilt inverted
                    if abs(dx) > 2 or abs(dy) > 2:
                        cv2.arrowedLine(overlay, (ex, ey), (ex + dx, ey + dy), col, 1, cv2.LINE_AA, tipLength=0.22)
                except Exception:
                    pass

        self._rgb = overlay
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        # shell
        r = self.rect().adjusted(0, 0, -1, -1)
        painter.setPen(QPen(QColor(COLORS["border"]), 1))
        painter.setBrush(QColor(COLORS["surface"]))
        painter.drawRoundedRect(r, 8, 8)

        if not hasattr(self, "_rgb") or self._rgb is None:
            painter.setPen(QColor(COLORS["muted"]))
            painter.drawText(r, Qt.AlignCenter, "No frame — press RUN")
            return

        # header bar inside shell
        header_h = 28
        header_rect = QRect(1, 1, self.width() - 2, header_h)
        painter.fillRect(header_rect, QColor(COLORS["faint"]))
        painter.setPen(QPen(QColor(COLORS["border"]), 1))
        painter.drawLine(header_rect.bottomLeft(), header_rect.bottomRight())

        # header title left
        painter.setPen(QColor(COLORS["text"]))
        f_title = QFont("Inter, Segoe UI", 8)
        f_title.setWeight(QFont.DemiBold)
        f_title.setLetterSpacing(QFont.AbsoluteSpacing, 0.6)
        painter.setFont(f_title)
        painter.drawText(header_rect.adjusted(10, 0, 0, 0), Qt.AlignVCenter, self.title)

        meta = self._meta

        # image area — now takes full remaining height (footer/legend removed per request)
        pad = 8
        avail = QRect(pad, header_h + pad, self.width() - pad * 2, self.height() - header_h - pad * 2)
        scale = min(avail.width() / self._w, avail.height() / self._h)
        disp_w = int(self._w * scale)
        disp_h = int(self._h * scale)
        ox = avail.x() + (avail.width() - disp_w) // 2
        oy = avail.y() + (avail.height() - disp_h) // 2

        # checker behind image (light)
        painter.fillRect(QRect(ox, oy, disp_w, disp_h), QColor("#F8FAFC"))
        painter.setPen(QPen(QColor(COLORS["border"]), 1))
        painter.drawRect(QRect(ox, oy, disp_w, disp_h))

        qimg = QImage(self._rgb.data, self._w, self._h, self._w * 3, QImage.Format_RGB888)
        pix = QPixmap.fromImage(qimg).scaled(disp_w, disp_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        painter.drawPixmap(ox, oy, pix)

        # --- HUD corners (painted over image in widget coords) ---
        # Map image coords to widget: helper
        def img_to_widget(ix, iy):
            return ox + int(ix * scale), oy + int(iy * scale)

        # TL: confidence pill
        if self._detection and self._detection.valid:
            det = self._detection
            pill = f"DET  {det.confidence*100:.0f}%  •  {det.area:.0f}px²"
            self._draw_pill(painter, QRect(ox + 6, oy + 6, 1, 1), pill, QColor(COLORS["det"]), QColor("#FFFFFF"))

        # TR: state pill
        if self._estimate:
            st = self._estimate.tracking_state.value
            col = QColor({"LOCKED":"#15803D","ACQUIRING":"#2563EB","SEARCHING":"#475569","CANDIDATE":"#475569","TEMP_LOST":"#A16207","REACQUIRING":"#A16207","FAILED":"#B91C1C"}.get(st, "#64748B"))
            self._draw_pill(painter, QRect(0,0,1,1), st, col, QColor("#FFFFFF"), align_right=True, anchor_x=ox+disp_w-6, anchor_y=oy+6)

        # BL: image coordinates of detection/estimate
        if self._detection and self._detection.valid and self._detection.centroid_px:
            cx, cy = self._detection.centroid_px
            txt = f"x {cx:.1f}  y {cy:.1f}"
            self._draw_hud_text(painter, ox + 6, oy + disp_h - 18, txt, QColor(COLORS["text2"]), QColor(255,255,255,210))

        # BR: scale bar (60px ~ 0.375° at 4°/640) — kept as in-image HUD
        bar_px = int(60 * scale)
        bar_x = ox + disp_w - bar_px - 8
        bar_y = oy + disp_h - 8
        painter.setPen(QPen(QColor(COLORS["text2"]), 1))
        painter.setBrush(QColor(COLORS["text2"]))
        painter.drawRect(QRect(bar_x, bar_y, bar_px, 3))
        painter.setPen(QColor(COLORS["muted"]))
        f_small = QFont("Inter", 6)
        painter.setFont(f_small)
        painter.drawText(QRect(bar_x - 28, bar_y - 10, 60, 10), Qt.AlignCenter, "60px")
        # footer legend + timestamp removed per request

    def _draw_pill(self, p, rect, text, bg, fg, align_right=False, anchor_x=None, anchor_y=None):
        fm = p.fontMetrics()
        # measure
        w = fm.horizontalAdvance(text) + 16
        h = 18
        if align_right:
            x = anchor_x - w
            y = anchor_y
        else:
            x = rect.x()
            y = rect.y()
        r = QRect(x, y, w, h)
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, 9, 9)
        p.setPen(fg)
        f = QFont("Inter", 7)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.drawText(r, Qt.AlignCenter, text)
        return r

    def _draw_hud_text(self, p, x, y, text, fg, bg):
        fm = p.fontMetrics()
        w = fm.horizontalAdvance(text) + 8
        h = 14
        r = QRect(x, y, w, h)
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, 4, 4)
        p.setPen(fg)
        f = QFont("JetBrains Mono, Consolas", 7)
        p.setFont(f)
        p.drawText(r, Qt.AlignCenter, text)


class WorldView(QWidget):
    def __init__(self, world_size=(2000, 2000), parent=None):
        super().__init__(parent)
        self.world_w, self.world_h = world_size
        self.camera_bounds = None
        self.camera_center = (world_size[0]/2, world_size[1]/2)
        self.world_pos = None
        self.trail = []
        self.setMinimumSize(560, 420)
        from PyQt5.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background: {COLORS['surface']}; border: 1px solid {COLORS['border']}; border-radius: 8px;")

    def update_state(self, camera, world_pos, trail=None):
        if camera is not None:
            self.camera_bounds = camera.get_viewport_bounds()
            self.camera_center = tuple(camera.center_world)
        if world_pos is not None:
            self.world_pos = world_pos
            self.trail.append(tuple(world_pos))
            if len(self.trail) > 220:
                self.trail.pop(0)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)

        outer = self.rect().adjusted(0, 0, -1, -1)
        p.setPen(QPen(QColor(COLORS["border"]), 1))
        p.setBrush(QColor(COLORS["surface"]))
        p.drawRoundedRect(outer, 8, 8)

        # header
        header_h = 28
        hdr = QRect(1, 1, self.width() - 2, header_h)
        p.fillRect(hdr, QColor(COLORS["faint"]))
        p.setPen(QPen(QColor(COLORS["border"]), 1))
        p.drawLine(hdr.bottomLeft(), hdr.bottomRight())
        p.setPen(QColor(COLORS["text"]))
        f_title = QFont("Inter, Segoe UI", 8)
        f_title.setWeight(QFont.DemiBold)
        f_title.setLetterSpacing(QFont.AbsoluteSpacing, 0.6)
        p.setFont(f_title)
        p.drawText(hdr.adjusted(10, 0, 0, 0), Qt.AlignVCenter, "WORLD FOV")

        if self.camera_bounds is None:
            p.setPen(QColor(COLORS["muted"]))
            p.drawText(self.rect(), Qt.AlignCenter, "Waiting for camera…")
            return

        pad = 10
        avail = QRect(pad, header_h + pad, self.width() - pad*2, self.height() - header_h - pad*2 - 22)
        scale = min(avail.width() / self.world_w, avail.height() / self.world_h)
        ox = avail.x() + (avail.width() - self.world_w * scale) // 2
        oy = avail.y() + (avail.height() - self.world_h * scale) // 2

        # world plate
        world_rect = QRect(int(ox), int(oy), int(self.world_w * scale), int(self.world_h * scale))
        p.setPen(QPen(QColor(COLORS["border"]), 1))
        p.setBrush(QColor("#F8FAFC"))
        p.drawRoundedRect(world_rect, 6, 6)

        # grid — light hairline, every 400px
        p.setPen(QPen(QColor("#E2E8F0"), 1, Qt.SolidLine))
        step = 400
        for gx in range(step, self.world_w, step):
            x = ox + gx * scale
            p.drawLine(int(x), world_rect.top(), int(x), world_rect.bottom())
            # tick label
            p.setPen(QColor(COLORS["subtle"]))
            f_tick = QFont("Inter", 6)
            p.setFont(f_tick)
            p.drawText(QRect(int(x) - 14, world_rect.bottom() + 2, 28, 10), Qt.AlignHCenter, str(gx))
            p.setPen(QPen(QColor("#E2E8F0"), 1))
        for gy in range(step, self.world_h, step):
            y = oy + gy * scale
            p.drawLine(world_rect.left(), int(y), world_rect.right(), int(y))
            p.setPen(QColor(COLORS["subtle"]))
            p.drawText(QRect(world_rect.right() + 2, int(y) - 5, 28, 10), Qt.AlignVCenter, str(gy))
            p.setPen(QPen(QColor("#E2E8F0"), 1))

        # axes — north arrow
        p.setPen(QPen(QColor(COLORS["text2"]), 1))
        p.setBrush(QColor(COLORS["text2"]))
        arrow = QRect(world_rect.right() - 28, world_rect.top() + 8, 16, 16)
        # N
        p.setPen(QColor(COLORS["muted"]))
        f_n = QFont("Inter", 7)
        f_n.setWeight(QFont.Bold)
        p.setFont(f_n)
        p.drawText(arrow, Qt.AlignCenter, "N")
        p.setPen(QPen(QColor(COLORS["text2"]), 1))
        p.drawLine(arrow.center().x(), arrow.bottom() + 2, arrow.center().x(), arrow.bottom() + 10)
        pts = [arrow.center() + p for p in [QPoint(0,-6), QPoint(-4,0), QPoint(4,0)] ]  # not used

        # trail — amber with fade
        if len(self.trail) > 1:
            for i in range(1, len(self.trail)):
                a = i / len(self.trail)
                alpha = int(40 + 160 * a)
                col = QColor(217, 119, 6, alpha)
                p.setPen(QPen(col, 2 if a > 0.85 else 1, Qt.SolidLine, Qt.RoundCap))
                x0 = ox + self.trail[i-1][0] * scale
                y0 = oy + self.trail[i-1][1] * scale
                x1 = ox + self.trail[i][0] * scale
                y1 = oy + self.trail[i][1] * scale
                p.drawLine(int(x0), int(y0), int(x1), int(y1))

        # camera footprint — blue, with header label
        if self.camera_bounds:
            l, t, r, b = self.camera_bounds
            frect = QRect(int(ox + l * scale), int(oy + t * scale), int((r - l) * scale), int((b - t) * scale))
            p.setPen(QPen(QColor(COLORS["footprint"]), 1.2))
            p.setBrush(QColor(37, 99, 235, 22))
            p.drawRoundedRect(frect, 3, 3)
            # footprint label
            lbl = f"CAM  {int(r-l)}×{int(b-t)}  pan {((self.camera_center[0]-self.world_w/2)/220):+.2f}° tilt {(-(self.camera_center[1]-self.world_h/2)/220):+.2f}°"
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(lbl) + 10
            bg = QRect(frect.x(), frect.y() - 16, min(tw, frect.width()), 14)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(37, 99, 235))
            p.drawRoundedRect(bg, 4, 4)
            p.setPen(QColor("#FFFFFF"))
            f_lbl = QFont("Inter", 6)
            f_lbl.setWeight(QFont.DemiBold)
            p.setFont(f_lbl)
            p.drawText(bg, Qt.AlignCenter, lbl)
            # boresight
            cx = ox + (l + r) / 2 * scale
            cy = oy + (t + b) / 2 * scale
            p.setPen(QPen(QColor(COLORS["footprint"]), 1))
            p.setBrush(QColor("#FFFFFF"))
            p.drawEllipse(int(cx - 3), int(cy - 3), 6, 6)
            p.setPen(QPen(QColor(COLORS["footprint"]), 1))
            p.drawLine(int(cx - 9), int(cy), int(cx - 3), int(cy))
            p.drawLine(int(cx + 3), int(cy), int(cx + 9), int(cy))
            p.drawLine(int(cx), int(cy - 9), int(cx), int(cy - 3))
            p.drawLine(int(cx), int(cy + 3), int(cx), int(cy + 9))

        # target — amber diamond with label
        if self.world_pos:
            tx = ox + self.world_pos[0] * scale
            ty = oy + self.world_pos[1] * scale
            # diamond
            p.setPen(QPen(QColor("#92400E"), 1.2))
            p.setBrush(QColor("#F59E0B"))
            p.save()
            p.translate(int(tx), int(ty))
            p.rotate(45)
            p.drawRect(-6, -6, 12, 12)
            p.restore()
            # callout
            txt = f"BEACON  {self.world_pos[0]:.0f}, {self.world_pos[1]:.0f}"
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(txt) + 10
            cr = QRect(int(tx) + 10, int(ty) - 18, tw, 14)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#FFFBEB"))
            p.setPen(QPen(QColor("#F59E0B"), 1))
            p.drawRoundedRect(cr, 4, 4)
            p.setPen(QColor("#92400E"))
            f_call = QFont("JetBrains Mono, Consolas", 6)
            p.setFont(f_call)
            p.drawText(cr, Qt.AlignCenter, txt)

        # footer — scale bar + legend
        footer = QRect(pad, self.height() - 18, self.width() - pad*2, 14)
        # scale bar: 400px world ~ scale*400 widget
        bar_w = int(400 * scale)
        bar_x = footer.x()
        bar_y = footer.y() + 6
        p.setPen(QPen(QColor(COLORS["text2"]), 1))
        p.setBrush(QColor(COLORS["text2"]))
        p.drawRect(QRect(bar_x, bar_y, bar_w, 3))
        p.setPen(QPen(QColor(COLORS["text2"]), 1))
        p.drawLine(bar_x, bar_y, bar_x, bar_y - 4)
        p.drawLine(bar_x + bar_w, bar_y, bar_x + bar_w, bar_y - 4)
        p.setPen(QColor(COLORS["muted"]))
        f_sc = QFont("Inter", 6)
        p.setFont(f_sc)
        p.drawText(QRect(bar_x, bar_y - 14, bar_w, 10), Qt.AlignCenter, "400 px")
        # legend right
        p.setPen(QColor(COLORS["subtle"]))
        f_leg = QFont("Inter", 6)
        f_leg.setLetterSpacing(QFont.AbsoluteSpacing, 0.3)
        p.setFont(f_leg)
        p.drawText(footer, Qt.AlignRight | Qt.AlignVCenter, "— beacon trail • blue = camera FOV  •  + boresight")
