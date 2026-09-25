"""
Target tracks & identity panel — Plan §16.5.

Live table with one row per candidate: ID, Class, Identity, Signature,
State, Age, Last seen, Primary confidence. Selecting a row highlights
track in Camera/World views. Below the table, evidence checklist for
selected track.

Colors per Plan §15: yellow candidate, cyan predicted, green primary,
red decoy, gray unknown, magenta GT (debug only).
"""
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QHBoxLayout, QFrame
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QBrush
from .theme import COLORS

STATE_COLORS_AI = {
    "PRIMARY_CONFIRMED": "#15803D",
    "DECOY_CONFIRMED": "#B91C1C",
    "IDENTITY_CHECKING": "#2563EB",
    "CANDIDATE_FOUND": "#CA8A04",
    "UNKNOWN": "#64748B",
    "SEARCHING": "#475569",
}

class TracksView(QWidget):
    trackSelected = pyqtSignal(int)  # track_id

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        title = QLabel("TARGET TRACKS")
        title.setStyleSheet(f"color:{COLORS['muted']}; font-size:11px; font-weight:700; letter-spacing:0.7px;")
        lay.addWidget(title)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["ID", "Class", "Primary %", "Signature", "State", "Age", "Missed"])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Stretch)
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 44)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setStyleSheet(f"""
            QTableWidget {{ background:{COLORS['surface']}; border:1px solid {COLORS['border']}; border-radius:6px; font-size:11px; }}
            QHeaderView::section {{ background:{COLORS['faint']}; color:{COLORS['muted']}; font-size:10px; font-weight:700; padding:4px; border:none; border-bottom:1px solid {COLORS['border']}; }}
        """)
        self.table.setMinimumHeight(140)
        self.table.setMaximumHeight(180)
        self.table.cellClicked.connect(self._on_click)
        lay.addWidget(self.table)

        # evidence panel
        self.evidence_frame = QFrame()
        self.evidence_frame.setStyleSheet(f"background:{COLORS['faint']}; border:1px solid {COLORS['border']}; border-radius:6px;")
        ev_lay = QVBoxLayout(self.evidence_frame)
        ev_lay.setContentsMargins(8, 6, 8, 6)
        ev_lay.setSpacing(2)
        ev_title = QLabel("IDENTITY EVIDENCE  (selected track)")
        ev_title.setStyleSheet(f"color:{COLORS['muted']}; font-size:10px; font-weight:700;")
        ev_lay.addWidget(ev_title)
        self.evidence_labels = []
        for _ in range(5):
            lbl = QLabel("—")
            lbl.setStyleSheet(f"color:{COLORS['text']}; font-size:11px;")
            lbl.setWordWrap(True)
            ev_lay.addWidget(lbl)
            self.evidence_labels.append(lbl)
        lay.addWidget(self.evidence_frame)

        self._tracks = []
        self._selected_id = None

    def update_tracks(self, ai_results, ai_tracks_dict):
        """
        ai_results: List[(Candidate, IdentityResult)]
        ai_tracks_dict: Dict[int, TrackState]
        """
        self._tracks = list(ai_results or [])
        self.table.setRowCount(len(self._tracks))
        for row, (cand, ident) in enumerate(self._tracks):
            # ID
            item = QTableWidgetItem(f"{cand.candidate_id:02d}")
            item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, item)
            # Class
            cls = getattr(ident, 'identity_state', None)
            cls_str = cls.value if hasattr(cls, 'value') else str(cls)
            # detect BEACON_LIKE vs DECOY
            det_cls = getattr(cand, 'detection_class', None)
            det_str = det_cls.value if hasattr(det_cls, 'value') else (det_cls or "UNKNOWN")
            self.table.setItem(row, 1, QTableWidgetItem(det_str))
            # Primary %
            prim = ident.primary_probability if ident else 0.0
            it = QTableWidgetItem(f"{prim*100:.0f}%")
            it.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 2, it)
            # Signature
            sig = getattr(getattr(ident, 'evidence', None), 'optical_signature_score', 0.0) if ident else 0.0
            sig_item = QTableWidgetItem(f"{sig*100:.0f}%" if ident else "—")
            sig_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 3, sig_item)
            # State
            state_item = QTableWidgetItem(cls_str)
            col = STATE_COLORS_AI.get(cls_str, COLORS['muted'])
            state_item.setForeground(QBrush(QColor(col)))
            self.table.setItem(row, 4, state_item)
            # Age
            tr = ai_tracks_dict.get(cand.candidate_id) if ai_tracks_dict else None
            age = getattr(tr, 'age', 0) if tr else 0
            self.table.setItem(row, 5, QTableWidgetItem(f"{age}"))
            # Missed
            missed = getattr(tr, 'missed_frames', 0) if tr else 0
            self.table.setItem(row, 6, QTableWidgetItem(f"{missed}"))
            # row background tint per state
            row_col = QColor(col)
            row_col.setAlpha(18)
            for col_idx in range(7):
                it2 = self.table.item(row, col_idx)
                if it2:
                    it2.setBackground(QBrush(row_col))
        # keep selection
        if self._selected_id is not None:
            for r, (c, _) in enumerate(self._tracks):
                if c.candidate_id == self._selected_id:
                    self.table.selectRow(r)
                    self._show_evidence_for(self._selected_id)
                    break

    def _on_click(self, row, col):
        if row < len(self._tracks):
            cand, ident = self._tracks[row]
            self._selected_id = cand.candidate_id
            self.trackSelected.emit(cand.candidate_id)
            self._show_evidence_for(cand.candidate_id)

    def _show_evidence_for(self, track_id):
        # find ident for track_id
        for cand, ident in self._tracks:
            if cand.candidate_id == track_id and ident:
                reasons = getattr(getattr(ident, 'evidence', None), 'reasons', []) or []
                # pad to 5 lines
                for i, lbl in enumerate(self.evidence_labels):
                    if i < len(reasons):
                        txt = reasons[i]
                        # color check/x
                        if txt.startswith("✓"):
                            lbl.setStyleSheet(f"color:#15803D; font-size:11px; font-weight:600;")
                        elif txt.startswith("✗"):
                            lbl.setStyleSheet(f"color:#B91C1C; font-size:11px;")
                        else:
                            lbl.setStyleSheet(f"color:{COLORS['text']}; font-size:11px;")
                        lbl.setText(txt)
                    else:
                        lbl.setText("—")
                        lbl.setStyleSheet(f"color:{COLORS['subtle']}; font-size:11px;")
                return
        for lbl in self.evidence_labels:
            lbl.setText("—")

    def clear(self):
        self.table.setRowCount(0)
        for lbl in self.evidence_labels:
            lbl.setText("—")
