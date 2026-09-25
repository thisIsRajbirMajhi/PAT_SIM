import logging

import cv2
import numpy as np
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QRect, QPoint
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont, QBrush
from .theme import COLORS


LOGGER = logging.getLogger(__name__)

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
        # AI multi-candidate overlays (Plan §16.3)
        self._ai_candidates = []  # List[Candidate]
        self._ai_results = []     # List[(Candidate, IdentityResult)]
        self.setMinimumSize(560, 420)
        from PyQt5.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            f"background: {COLORS['surface']}; border: 1px solid {COLORS['border']}; "
            "border-radius: 8px;"
        )

    def set_ai_overlays(self, candidates, results):
        self._ai_candidates = list(candidates or [])
        self._ai_results = list(results or [])

    def clear_ai_overlays(self):
        self._ai_candidates = []
        self._ai_results = []

    def set_frame(self, frame_gray, detection=None, estimate=None, world_camera=None, show_overlays=True, meta=None, centre_offset=None):
        if frame_gray is None:
            return
        h, w = frame_gray.shape[:2]
        self._w, self._h = w, h
        self._detection = detection
        self._estimate = estimate
        self._meta = meta or {}
        # Video centre calibration: offset in pixels from frame centre (for videos where principal point != geometric centre)
        self._centre_offset = centre_offset  # (dx, dy) or None
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

        # Sr.2 Camera Type: handle both monochrome (gray) and colour (BGR)
        if len(frame_gray.shape) == 3:
            rgb = cv2.cvtColor(frame_gray, cv2.COLOR_BGR2RGB)
        else:
            rgb = cv2.cvtColor(frame_gray, cv2.COLOR_GRAY2RGB)
        overlay = rgb.copy()

        if show_overlays:
            # Video centre calibration: use calibrated centre if provided (for videos where principal point != frame centre)
            if getattr(self, '_centre_offset', None) and self._centre_offset is not None:
                try:
                    dx, dy = self._centre_offset
                    cx, cy = int(w // 2 + float(dx)), int(h // 2 + float(dy))
                    # Clamp to stay inside image
                    cx = max(0, min(w - 1, cx))
                    cy = max(0, min(h - 1, cy))
                except:
                    cx, cy = w // 2, h // 2
            else:
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

            # --- reticle: precise crosshair with a subtle range ring ---
            if self.show_reticle:
                cv2.circle(overlay, (cx, cy), 26, (70, 100, 145), 1, cv2.LINE_AA)
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

            # --- AI multi-candidate overlays (Plan §16.3) ---
            if getattr(self, '_ai_results', None):
                # map identity state -> BGR color + label
                for c, ident in self._ai_results:
                    st = ident.identity_state.value if ident else "UNKNOWN"
                    if st == "PRIMARY_CONFIRMED":
                        col = (40, 180, 70)   # green
                    elif st == "DECOY_CONFIRMED":
                        col = (38, 38, 220)   # red
                    elif st == "UNKNOWN":
                        col = (139, 116, 100) # gray
                    elif st == "IDENTITY_CHECKING":
                        col = (212, 182, 6)   # cyan/ amber
                    else:
                        col = (8, 179, 234)   # yellow candidate
                    bx, by, bw, bh = c.bbox
                    # Slightly heavier box and corner accents make small
                    # candidates readable without covering the sensor image.
                    cv2.rectangle(overlay, (bx, by), (bx + bw, by + bh), col, 2, cv2.LINE_AA)
                    corner = max(4, min(10, int(min(bw, bh) * 0.35)))
                    for x0, y0, sx, sy in (
                        (bx, by, 1, 1),
                        (bx + bw, by, -1, 1),
                        (bx, by + bh, 1, -1),
                        (bx + bw, by + bh, -1, -1),
                    ):
                        cv2.line(overlay, (x0, y0), (x0 + sx * corner, y0), col, 2, cv2.LINE_AA)
                        cv2.line(overlay, (x0, y0), (x0, y0 + sy * corner), col, 2, cv2.LINE_AA)
                    # ID + score
                    label = f"ID{c.candidate_id} {st[:3]} {ident.primary_probability*100:.0f}%" if ident else f"ID{c.candidate_id}"
                    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.38, 1)
                    ly = max(th + 5, by - 4)
                    cv2.rectangle(overlay, (bx, ly - th - 5), (bx + tw + 6, ly + 2), (12, 18, 28), -1)
                    cv2.putText(overlay, label, (bx + 3, ly - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.38, col, 1, cv2.LINE_AA)
                    # centroid dot
                    x, y = int(round(c.centroid_px[0])), int(round(c.centroid_px[1]))
                    cv2.circle(overlay, (x, y), 4, col, -1, cv2.LINE_AA)
                    cv2.circle(overlay, (x, y), 7, col, 1, cv2.LINE_AA)
            elif getattr(self, '_ai_candidates', None):
                for c in self._ai_candidates:
                    bx, by, bw, bh = c.bbox
                    cv2.rectangle(overlay, (bx, by), (bx + bw, by + bh), (8, 179, 234), 1, cv2.LINE_AA)
                    cv2.circle(overlay, (int(c.centroid_px[0]), int(c.centroid_px[1])), 4, (8, 179, 234), -1, cv2.LINE_AA)
            # --- detection: bbox + cross + label (classical fallback when AI disabled) ---
            if (not getattr(self, '_ai_results', None) and not getattr(self, '_ai_candidates', None)) and detection and detection.valid and detection.centroid_px:
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
                except Exception as exc:
                    LOGGER.debug("Could not draw velocity vector: %s", exc)
                # Fused error vector is useful in both AI and classical modes.
                if self.show_reticle and (abs(ex - cx) > 2 or abs(ey - cy) > 2):
                    cv2.line(overlay, (cx, cy), (ex, ey), col, 1, cv2.LINE_AA)
                    mx, my = (cx + ex) // 2, (cy + ey) // 2
                    err = np.hypot(ex - cx, ey - cy)
                    cv2.putText(
                        overlay,
                        f"FUSED {err:.0f}px",
                        (mx + 6, my - 6),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.36,
                        col,
                        1,
                        cv2.LINE_AA,
                    )

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

        # Header bar inside shell.  The right-side metadata stays outside the
        # sensor image so it never competes with candidate labels.
        header_h = 32
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
        header_meta = [
            str(meta.get("res", "")),
            str(meta.get("fov", "")),
            str(meta.get("fps", "")),
        ]
        cursor_x = header_rect.right() - 8
        f_meta = QFont("JetBrains Mono, Consolas", 7)
        f_meta.setWeight(QFont.DemiBold)
        painter.setFont(f_meta)
        for text in reversed([v for v in header_meta if v]):
            tw = painter.fontMetrics().horizontalAdvance(text) + 14
            cursor_x -= tw
            badge = QRect(cursor_x, header_rect.y() + 7, tw, 18)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#EFF6FF"))
            painter.drawRoundedRect(badge, 5, 5)
            painter.setPen(QColor("#1D4ED8"))
            painter.drawText(badge, Qt.AlignCenter, text)
            cursor_x -= 5

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

        # Compact sensor HUD card.  It gives the operator a stable reading
        # surface while keeping the video itself visually quiet.
        hud_lines = [
            f"SENSOR  {meta.get('res', '—')}",
            f"FRAME   {meta.get('frame_id', '—')}",
            f"TRACKS  {len(self._ai_results) if self._ai_results else (len(self._ai_candidates) if self._ai_candidates else 1 if self._detection and self._detection.valid else 0)}",
        ]
        self._draw_info_card(
            painter,
            QRect(ox + 8, oy + 32, 126, 54),
            hud_lines,
            QColor(10, 18, 30, 205),
            QColor("#DBEAFE"),
        )

        # BL: image coordinates of detection/estimate
        if self._detection and self._detection.valid and self._detection.centroid_px:
            cx, cy = self._detection.centroid_px
            txt = f"x {cx:.1f}  y {cy:.1f}"
            self._draw_hud_text(painter, ox + 6, oy + disp_h - 18, txt, QColor(COLORS["text2"]), QColor(255,255,255,210))

        # BR: scale bar (60px ~ 0.375° at 4°/640)
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
        # Bottom-right processing state
        footer_txt = "AI TRACKING" if self._ai_results else "CLASSICAL DETECTION"
        self._draw_hud_text(
            painter,
            ox + disp_w - 142,
            oy + disp_h - 26,
            footer_txt,
            QColor("#E2E8F0"),
            QColor(15, 23, 42, 205),
        )

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

    def _draw_info_card(self, p, rect, lines, bg, fg):
        p.setPen(QPen(QColor(148, 163, 184, 90), 1))
        p.setBrush(bg)
        p.drawRoundedRect(rect, 6, 6)
        font = QFont("JetBrains Mono, Consolas", 6)
        font.setWeight(QFont.DemiBold)
        p.setFont(font)
        p.setPen(fg)
        line_h = max(12, rect.height() // max(1, len(lines)))
        for i, line in enumerate(lines):
            p.drawText(
                QRect(rect.x() + 8, rect.y() + 4 + i * line_h, rect.width() - 16, line_h),
                Qt.AlignLeft | Qt.AlignVCenter,
                str(line),
            )


class WorldView(QWidget):
    def __init__(self, world_size=(2000, 2000), parent=None):
        super().__init__(parent)
        self.world_w, self.world_h = world_size
        self.camera_bounds = None
        self.camera_center = (world_size[0]/2, world_size[1]/2)
        self.world_pos = None
        self.trail = []
        # AI multi-target decoy trails (Plan §16.4)
        self.decoy_trails = {}  # track_id -> list[(x,y)]
        self.ai_tracks_snapshot = []
        self.setMinimumSize(560, 420)
        from PyQt5.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            f"background: {COLORS['surface']}; border: 1px solid {COLORS['border']}; "
            "border-radius: 8px;"
        )

    def update_state(self, camera, world_pos, trail=None, ai_tracks=None):
        if camera is not None:
            self.camera_bounds = camera.get_viewport_bounds()
            self.camera_center = tuple(camera.center_world)
        if world_pos is not None:
            self.world_pos = world_pos
            self.trail.append(tuple(world_pos))
            if len(self.trail) > 220:
                self.trail.pop(0)
        # AI decoy trails
        if ai_tracks is not None:
            self.ai_tracks_snapshot = list(ai_tracks)
            for tr in ai_tracks:
                tid = getattr(tr, 'track_id', None)
                if tid is None:
                    continue
                last = tr.position_history[-1] if getattr(tr, 'position_history', None) else None
                if last is None:
                    continue
                self.decoy_trails.setdefault(tid, []).append(tuple(last))
                if len(self.decoy_trails[tid]) > 120:
                    self.decoy_trails[tid].pop(0)
            # prune missing tracks
            alive = {getattr(t, 'track_id', -1) for t in ai_tracks}
            for k in list(self.decoy_trails.keys()):
                if k not in alive:
                    self.decoy_trails.pop(k, None)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)

        outer = self.rect().adjusted(0, 0, -1, -1)
        p.setPen(QPen(QColor(COLORS["border"]), 1))
        p.setBrush(QColor(COLORS["surface"]))
        p.drawRoundedRect(outer, 8, 8)

        # Header with map identity and live context badges.
        header_h = 32
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

        badges = [
            f"WORLD {int(self.world_w)}×{int(self.world_h)}",
            "CAMERA FOOTPRINT",
            f"TRACKS {len(self.ai_tracks_snapshot)}",
        ]
        right = hdr.right() - 8
        badge_font = QFont("JetBrains Mono, Consolas", 7)
        badge_font.setWeight(QFont.DemiBold)
        p.setFont(badge_font)
        for text in reversed(badges):
            tw = p.fontMetrics().horizontalAdvance(text) + 14
            right -= tw
            badge = QRect(right, hdr.y() + 7, tw, 18)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#EFF6FF"))
            p.drawRoundedRect(badge, 5, 5)
            p.setPen(QColor("#1D4ED8"))
            p.drawText(badge, Qt.AlignCenter, text)
            right -= 5

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

        # Grid — minor 200px guides plus stronger 400px guides.
        minor_step = 200
        p.setPen(QPen(QColor(226, 232, 240, 120), 1, Qt.DotLine))
        for gx in range(minor_step, self.world_w, minor_step):
            x = ox + gx * scale
            p.drawLine(int(x), world_rect.top(), int(x), world_rect.bottom())
        for gy in range(minor_step, self.world_h, minor_step):
            y = oy + gy * scale
            p.drawLine(world_rect.left(), int(y), world_rect.right(), int(y))

        # Major grid and coordinate labels.
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
        # Map status card: a stable visual anchor for the operator.
        self._draw_map_card(
            p,
            QRect(world_rect.left() + 8, world_rect.top() + 8, 160, 58),
            [
                "WORLD MAP  /  LIVE",
                f"CAMERA  {int(self.world_w * scale):d}px view",
                f"PRIMARY  {'VISIBLE' if self.world_pos else 'SEARCHING'}",
            ],
        )

        # trail — amber with fade (primary)
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
        # AI decoy trails (red / gray per identity)
        if getattr(self, 'decoy_trails', None):
            for tid, trail in self.decoy_trails.items():
                if len(trail) < 2:
                    continue
                # find identity for color
                ident = None
                for tr in getattr(self, 'ai_tracks_snapshot', []):
                    if getattr(tr, 'track_id', None) == tid:
                        ident = getattr(tr, 'current_identity', None)
                        break
                ival = str(ident) if ident else "UNKNOWN"
                if "PRIMARY" in ival:
                    base_col = QColor(34, 150, 80, 160)
                elif "DECOY" in ival:
                    base_col = QColor(190, 40, 40, 140)
                else:
                    base_col = QColor(100, 116, 139, 120)
                for i in range(1, len(trail)):
                    p.setPen(QPen(base_col, 1, Qt.DotLine, Qt.RoundCap))
                    x0 = ox + trail[i-1][0] * scale
                    y0 = oy + trail[i-1][1] * scale
                    x1 = ox + trail[i][0] * scale
                    y1 = oy + trail[i][1] * scale
                    p.drawLine(int(x0), int(y0), int(x1), int(y1))
                # endpoint marker with ID
                if trail:
                    tx, ty = trail[-1]
                    px, py = ox + tx * scale, oy + ty * scale
                    p.setPen(QPen(base_col, 1))
                    p.setBrush(base_col)
                    p.drawEllipse(int(px)-3, int(py)-3, 6, 6)
                    p.setPen(QColor("#333333"))
                    f_id = QFont("JetBrains Mono, Consolas", 6)
                    p.setFont(f_id)
                    p.drawText(int(px)+6, int(py)-4, f"#{tid}")

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
            label_w = max(72, min(tw, max(72, frect.width())))
            label_y = max(world_rect.top() + 2, frect.y() - 16)
            bg = QRect(frect.x(), label_y, label_w, 14)
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
            p.setPen(QPen(QColor(COLORS["footprint"]), 1, Qt.DashLine))
            p.drawEllipse(int(cx - 14), int(cy - 14), 28, 28)

        # target — state-aware diamond with a readable callout.
        if self.world_pos:
            tx = ox + self.world_pos[0] * scale
            ty = oy + self.world_pos[1] * scale
            primary_confirmed = any(
                "PRIMARY" in str(getattr(tr, "current_identity", ""))
                for tr in self.ai_tracks_snapshot
            )
            target_fill = QColor("#16A34A") if primary_confirmed else QColor("#F59E0B")
            target_edge = QColor("#166534") if primary_confirmed else QColor("#92400E")
            # diamond
            p.setPen(QPen(target_edge, 1.4))
            p.setBrush(target_fill)
            p.save()
            p.translate(int(tx), int(ty))
            p.rotate(45)
            p.drawRect(-6, -6, 12, 12)
            p.restore()
            p.setPen(QPen(target_fill, 1))
            p.drawEllipse(int(tx) - 12, int(ty) - 12, 24, 24)
            # callout
            txt = f"{'PRIMARY' if primary_confirmed else 'BEACON'}  {self.world_pos[0]:.0f}, {self.world_pos[1]:.0f}"
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(txt) + 10
            callout_x = min(int(tx) + 10, world_rect.right() - tw - 4)
            callout_x = max(world_rect.left() + 4, callout_x)
            callout_y = max(world_rect.top() + 4, min(int(ty) - 18, world_rect.bottom() - 18))
            cr = QRect(callout_x, callout_y, tw, 14)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 235))
            p.setPen(QPen(target_fill, 1))
            p.drawRoundedRect(cr, 4, 4)
            p.setPen(target_edge)
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
        # Legend right with actual swatches instead of a text-only hint.
        legend_items = [
            (QColor("#D97706"), "target trail"),
            (QColor("#2563EB"), "camera FOV"),
            (QColor("#94A3B8"), "track trail"),
        ]
        f_leg = QFont("Inter", 6)
        p.setFont(f_leg)
        lx = footer.right() - 245
        for color, label in legend_items:
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawEllipse(lx, footer.y() + 3, 6, 6)
            p.setPen(QColor(COLORS["muted"]))
            p.drawText(QRect(lx + 9, footer.y(), 70, 14), Qt.AlignVCenter, label)
            lx += 78

    def _draw_map_card(self, p, rect, lines):
        p.setPen(QPen(QColor(148, 163, 184, 110), 1))
        p.setBrush(QColor(255, 255, 255, 230))
        p.drawRoundedRect(rect, 6, 6)
        font = QFont("JetBrains Mono, Consolas", 6)
        font.setWeight(QFont.DemiBold)
        p.setFont(font)
        for i, line in enumerate(lines):
            p.setPen(QColor("#334155") if i else QColor("#1D4ED8"))
            p.drawText(
                QRect(rect.x() + 8, rect.y() + 5 + i * 16, rect.width() - 16, 14),
                Qt.AlignLeft | Qt.AlignVCenter,
                str(line),
            )
