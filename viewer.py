"""Three-axis DICOM viewer widget."""

from __future__ import annotations

import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QSplitter, QLabel, QSlider, QSizePolicy,
)
from PyQt6.QtCore import Qt

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

_BG = "#111320"
_LABEL_COLOR = "#7fa8ff"


class _SliceView(QWidget):
    """Single orthogonal view: matplotlib canvas + position slider."""

    def __init__(self, label: str, axis: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.axis   = axis
        self.volume: np.ndarray | None = None
        self.wc     = 0.0
        self.ww     = 2000.0
        self._im    = None
        self._setup_ui(label)

    def _setup_ui(self, label: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        lbl = QLabel(label)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(
            f"color:{_LABEL_COLOR};font-weight:700;font-size:10px;letter-spacing:0.5px;"
        )
        layout.addWidget(lbl)

        self.fig = Figure(facecolor=_BG)
        self.fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
        self.ax  = self.fig.add_subplot(111)
        self.ax.set_facecolor(_BG)
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        for spine in self.ax.spines.values():
            spine.set_visible(False)

        self.canvas = FigureCanvas(self.fig)
        self.canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.canvas.installEventFilter(self)
        layout.addWidget(self.canvas, stretch=1)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(0)
        self.slider.valueChanged.connect(self._on_slider)
        layout.addWidget(self.slider)

        self.pos_lbl = QLabel("—")
        self.pos_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pos_lbl.setStyleSheet("color:#44495e;font-size:10px;")
        layout.addWidget(self.pos_lbl)

    # ── Public API ────────────────────────────────────────────────────────────

    def load(self, volume: np.ndarray, wc: float, ww: float) -> None:
        self.volume = volume
        self.wc = wc
        self.ww = ww
        self._im = None  # force re-creation of imshow
        n = volume.shape[self.axis]
        self.slider.blockSignals(True)
        self.slider.setMaximum(n - 1)
        self.slider.setValue(n // 2)
        self.slider.blockSignals(False)
        self._refresh(n // 2)

    def set_wl(self, wc: float, ww: float) -> None:
        self.wc = wc
        self.ww = ww
        self._refresh(self.slider.value())

    def clear(self) -> None:
        self.volume = None
        self._im    = None
        self.ax.clear()
        self.ax.set_facecolor(_BG)
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        self.slider.setMaximum(0)
        self.slider.setValue(0)
        self.pos_lbl.setText("—")
        self.canvas.draw_idle()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _get_slice(self, idx: int) -> np.ndarray:
        v = self.volume
        if   self.axis == 0: return v[idx, :, :]
        elif self.axis == 1: return np.flipud(v[:, idx, :])
        else:                return np.flipud(v[:, :, idx])

    def _on_slider(self, value: int) -> None:
        self._refresh(value)

    def _refresh(self, idx: int) -> None:
        if self.volume is None:
            return
        s    = self._get_slice(idx)
        vmin = self.wc - self.ww / 2.0
        vmax = self.wc + self.ww / 2.0

        if self._im is None:
            self.ax.clear()
            self.ax.set_facecolor(_BG)
            self.ax.set_xticks([])
            self.ax.set_yticks([])
            for sp in self.ax.spines.values():
                sp.set_visible(False)
            self._im = self.ax.imshow(
                s, cmap="gray", vmin=vmin, vmax=vmax,
                aspect="equal", interpolation="nearest", origin="upper",
            )
        else:
            self._im.set_data(s)
            self._im.set_clim(vmin, vmax)

        n = self.volume.shape[self.axis]
        self.pos_lbl.setText(f"{idx + 1} / {n}")
        self.canvas.draw_idle()

    def eventFilter(self, obj, event):  # type: ignore[override]
        """Scroll wheel changes slice."""
        from PyQt6.QtCore import QEvent
        if obj is self.canvas and event.type() == QEvent.Type.Wheel:
            delta = event.angleDelta().y()
            step  = 1 if delta > 0 else -1
            self.slider.setValue(
                max(0, min(self.slider.maximum(), self.slider.value() - step))
            )
            return True
        return super().eventFilter(obj, event)


class DicomViewer(QWidget):
    """Three-axis DICOM viewer (axial / coronal / sagittal)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        vsplit = QSplitter(Qt.Orientation.Vertical)
        vsplit.setStyleSheet("QSplitter::handle{background:#1e2135;height:5px;}")

        # Top row: large axial view
        self.axial = _SliceView("AXIAL  (Z)", axis=0)
        vsplit.addWidget(self.axial)

        # Bottom row: coronal + sagittal side by side
        hsplit = QSplitter(Qt.Orientation.Horizontal)
        hsplit.setStyleSheet("QSplitter::handle{background:#1e2135;width:5px;}")
        self.coronal   = _SliceView("CORONAL  (Y)", axis=1)
        self.sagittal  = _SliceView("SAGITTAL  (X)", axis=2)
        hsplit.addWidget(self.coronal)
        hsplit.addWidget(self.sagittal)
        vsplit.addWidget(hsplit)

        vsplit.setStretchFactor(0, 3)
        vsplit.setStretchFactor(1, 2)
        layout.addWidget(vsplit)

    def load_volume(self, volume: np.ndarray, wc: float, ww: float) -> None:
        for view in (self.axial, self.coronal, self.sagittal):
            view.load(volume, wc, ww)

    def set_wl(self, wc: float, ww: float) -> None:
        for view in (self.axial, self.coronal, self.sagittal):
            view.set_wl(wc, ww)

    def clear(self) -> None:
        for view in (self.axial, self.coronal, self.sagittal):
            view.clear()
