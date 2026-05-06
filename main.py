#!/usr/bin/env python3
"""DICOM Anonymizer — main application window."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Resolve Qt plugin path before any Qt import so macOS can find libqcocoa.dylib.
# This is needed when running from a conda/venv environment.
try:
    import PyQt6 as _pyqt6
    _qt_plugins = Path(_pyqt6.__file__).parent / "Qt6" / "plugins"
    if _qt_plugins.exists():
        os.environ.setdefault("QT_PLUGIN_PATH", str(_qt_plugins))
        os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", str(_qt_plugins / "platforms"))
except Exception:
    pass

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QGroupBox, QLabel, QLineEdit, QPushButton, QCheckBox,
    QSlider, QComboBox, QScrollArea, QFileDialog, QMessageBox,
    QStackedWidget, QRadioButton, QButtonGroup, QFrame, QToolBar,
    QSpinBox, QSizePolicy, QDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QDialogButtonBox,
)
from PyQt6.QtCore import Qt, QSettings, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QFont, QGuiApplication

import utils
import exact_client as ec
from viewer import DicomViewer

# ── Stylesheet ────────────────────────────────────────────────────────────────

STYLESHEET = """
QMainWindow { background:#111320; }

QWidget {
    background:#111320;
    color:#d8ddf0;
    font-size:13px;
}

/* ── panels ── */
QWidget#LeftPanel, QWidget#RightContainer {
    background:#171929;
    border-radius:0px;
}

/* ── group boxes ── */
QGroupBox {
    border:1px solid #252a42;
    border-radius:10px;
    margin-top:16px;
    padding:10px 8px 8px 8px;
    font-weight:700;
    color:#7fa8ff;
    font-size:12px;
    letter-spacing:0.4px;
}
QGroupBox::title {
    subcontrol-origin:margin;
    left:12px;
    padding:0 6px;
}

/* ── buttons ── */
QPushButton {
    background:#2d52c0;
    color:#fff;
    border:none;
    border-radius:8px;
    padding:8px 16px;
    font-weight:600;
    font-size:12px;
}
QPushButton:hover   { background:#3b63d4; }
QPushButton:pressed { background:#1f3d98; }
QPushButton:disabled { background:#1e2235; color:#404565; }

QPushButton#accent {
    background:#0f7d4b;
    color:#fff;
}
QPushButton#accent:hover   { background:#139962; }
QPushButton#accent:pressed { background:#0a5c38; }
QPushButton#accent:disabled { background:#1e2235; color:#404565; }

QPushButton#small {
    padding:5px 10px;
    font-size:11px;
    border-radius:6px;
    background:#252a42;
}
QPushButton#small:hover { background:#2e3560; }

/* ── inputs ── */
QLineEdit, QSpinBox {
    background:#1a1e30;
    border:1px solid #252a42;
    border-radius:7px;
    padding:6px 10px;
    color:#d8ddf0;
    selection-background-color:#2d52c0;
}
QLineEdit:focus, QSpinBox:focus { border-color:#4a78e8; }
QLineEdit:disabled { color:#404565; }

QComboBox {
    background:#1a1e30;
    border:1px solid #252a42;
    border-radius:7px;
    padding:6px 10px;
    color:#d8ddf0;
}
QComboBox:focus { border-color:#4a78e8; }
QComboBox::drop-down { border:none; width:26px; }
QComboBox QAbstractItemView {
    background:#1a1e30;
    selection-background-color:#2d52c0;
    border:1px solid #252a42;
}

/* ── sliders ── */
QSlider::groove:horizontal {
    height:4px;
    background:#252a42;
    border-radius:2px;
}
QSlider::handle:horizontal {
    width:14px; height:14px;
    background:#4a78e8;
    border-radius:7px;
    margin:-5px 0;
}
QSlider::sub-page:horizontal {
    background:#2d52c0;
    border-radius:2px;
}

/* ── check / radio ── */
QCheckBox, QRadioButton {
    color:#8890b0;
    spacing:6px;
    font-size:12px;
}
QCheckBox::indicator, QRadioButton::indicator {
    width:14px; height:14px;
    border:1px solid #252a42;
    border-radius:3px;
    background:#1a1e30;
}
QRadioButton::indicator { border-radius:7px; }
QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background:#2d52c0;
    border-color:#4a78e8;
}

/* ── scroll ── */
QScrollArea { border:none; }
QScrollBar:vertical {
    background:#111320;
    width:7px;
    border-radius:3px;
}
QScrollBar::handle:vertical {
    background:#252a42;
    border-radius:3px;
    min-height:20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }

/* ── status bar ── */
QStatusBar {
    background:#0c0f1c;
    color:#5a6080;
    font-size:11px;
    border-top:1px solid #1e2235;
    padding:2px 8px;
}

/* ── toolbar ── */
QToolBar {
    background:#0e1120;
    border-bottom:1px solid #1e2235;
    padding:4px 8px;
    spacing:6px;
}
QToolBar QToolButton {
    background:#1e2340;
    color:#d8ddf0;
    border:none;
    border-radius:7px;
    padding:6px 14px;
    font-size:12px;
    font-weight:600;
}
QToolBar QToolButton:hover   { background:#28304e; }
QToolBar QToolButton:pressed { background:#1a1e35; }

/* ── separators ── */
QFrame#Sep {
    background:#1e2235;
    max-height:1px;
    min-height:1px;
}

/* ── metadata labels ── */
QLabel#MetaKey { color:#44495e; font-size:11px; }
QLabel#MetaVal { color:#c0c6e0; font-size:12px; }
QLabel#SectionHead {
    color:#7fa8ff;
    font-weight:700;
    font-size:11px;
    letter-spacing:0.5px;
    margin-top:4px;
}
"""


# ── Helper widgets ────────────────────────────────────────────────────────────

def _sep() -> QFrame:
    f = QFrame()
    f.setObjectName("Sep")
    f.setFrameShape(QFrame.Shape.HLine)
    return f


class _InfoRow(QWidget):
    """One metadata key-value row."""

    def __init__(self, key: str) -> None:
        super().__init__()
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 1, 0, 1)
        h.setSpacing(6)
        k = QLabel(key)
        k.setObjectName("MetaKey")
        k.setFixedWidth(72)
        self._v = QLabel("—")
        self._v.setObjectName("MetaVal")
        self._v.setWordWrap(True)
        h.addWidget(k)
        h.addWidget(self._v, stretch=1)

    def set(self, val: str) -> None:
        self._v.setText(str(val).strip() if val else "—")


# ── Left panel (metadata display) ────────────────────────────────────────────

class _LeftPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("LeftPanel")
        self.setFixedWidth(240)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(10)

        # Series info
        grp1 = QGroupBox("Series")
        v1 = QVBoxLayout()
        v1.setSpacing(3)
        self.modality    = _InfoRow("Modality")
        self.study_date  = _InfoRow("Date")
        self.study_desc  = _InfoRow("Study")
        self.series_desc = _InfoRow("Series")
        self.dimensions  = _InfoRow("Size")
        for w in [self.modality, self.study_date, self.study_desc,
                  self.series_desc, self.dimensions]:
            v1.addWidget(w)
        grp1.setLayout(v1)
        outer.addWidget(grp1)

        # Patient info
        grp2 = QGroupBox("Original Patient")
        v2 = QVBoxLayout()
        v2.setSpacing(3)
        self.pt_name = _InfoRow("Name")
        self.pt_id   = _InfoRow("ID")
        self.pt_dob  = _InfoRow("DOB")
        self.pt_sex  = _InfoRow("Sex")
        self.pt_age  = _InfoRow("Age")
        for w in [self.pt_name, self.pt_id, self.pt_dob,
                  self.pt_sex, self.pt_age]:
            v2.addWidget(w)
        grp2.setLayout(v2)
        outer.addWidget(grp2)

        outer.addStretch()

    def update(self, meta: dict) -> None:
        self.modality.set(meta.get("modality", ""))
        self.study_date.set(meta.get("study_date", ""))
        self.study_desc.set(meta.get("study_description", ""))
        self.series_desc.set(meta.get("series_description", ""))
        sh = meta.get("volume_shape")
        self.dimensions.set(
            f"{sh[2]} × {sh[1]} × {sh[0]}" if sh else ""
        )
        self.pt_name.set(meta.get("patient_name", ""))
        self.pt_id.set(meta.get("patient_id", ""))
        self.pt_dob.set(meta.get("patient_dob", ""))
        self.pt_sex.set(meta.get("patient_sex", ""))
        self.pt_age.set(meta.get("patient_age", ""))


# ── Right panel (anonymisation + export) ─────────────────────────────────────

class _RightPanel(QScrollArea):
    # Signals emitted when the user acts
    wl_changed       = pyqtSignal(float, float)   # (center, width)
    export_nifti_req = pyqtSignal()
    connect_req      = pyqtSignal()
    export_exact_req = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFixedWidth(268)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        container.setObjectName("RightContainer")
        self.setWidget(container)

        v = QVBoxLayout(container)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(10)

        v.addWidget(self._build_anon_group())
        v.addWidget(self._build_exact_group())
        v.addStretch()

    # ── Anonymisation group ───────────────────────────────────────────────────

    def _build_anon_group(self) -> QGroupBox:
        grp = QGroupBox("Anonymisation")
        ag  = QVBoxLayout()
        ag.setSpacing(6)

        # Original name display
        orig_head = QLabel("ORIGINAL")
        orig_head.setObjectName("SectionHead")
        ag.addWidget(orig_head)
        self.orig_name_lbl = QLabel("—")
        self.orig_name_lbl.setWordWrap(True)
        self.orig_name_lbl.setStyleSheet("color:#c05060;font-size:12px;padding:2px 0;")
        ag.addWidget(self.orig_name_lbl)

        ag.addWidget(_sep())

        # Pseudonym field
        ps_head = QLabel("PSEUDONYM")
        ps_head.setObjectName("SectionHead")
        ag.addWidget(ps_head)

        name_row = QHBoxLayout()
        self.pseudo_edit = QLineEdit()
        self.pseudo_edit.setPlaceholderText("e.g. SwiftRiver")
        self.gen_btn = QPushButton("⟳")
        self.gen_btn.setObjectName("small")
        self.gen_btn.setFixedWidth(34)
        self.gen_btn.setToolTip("Generate random pseudonym")
        name_row.addWidget(self.pseudo_edit, stretch=1)
        name_row.addWidget(self.gen_btn)
        ag.addLayout(name_row)

        self.det_check = QCheckBox("Deterministic (hash of patient ID)")
        ag.addWidget(self.det_check)

        self.copy_btn = QPushButton("Copy Pseudonym")
        self.copy_btn.setObjectName("small")
        self.copy_btn.setEnabled(False)
        ag.addWidget(self.copy_btn)

        ag.addWidget(_sep())

        # Window / Level
        wl_head = QLabel("WINDOW / LEVEL")
        wl_head.setObjectName("SectionHead")
        ag.addWidget(wl_head)

        # WC
        wc_row = QHBoxLayout()
        wc_row.addWidget(QLabel("Center"))
        self.wc_val_lbl = QLabel("0")
        self.wc_val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.wc_val_lbl.setStyleSheet("color:#7fa8ff;font-size:11px;min-width:40px;")
        wc_row.addWidget(self.wc_val_lbl)
        ag.addLayout(wc_row)
        self.wc_slider = QSlider(Qt.Orientation.Horizontal)
        self.wc_slider.setRange(-4096, 8192)
        self.wc_slider.setValue(300)
        ag.addWidget(self.wc_slider)

        # WW
        ww_row = QHBoxLayout()
        ww_row.addWidget(QLabel("Width"))
        self.ww_val_lbl = QLabel("2000")
        self.ww_val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.ww_val_lbl.setStyleSheet("color:#7fa8ff;font-size:11px;min-width:40px;")
        ww_row.addWidget(self.ww_val_lbl)
        ag.addLayout(ww_row)
        self.ww_slider = QSlider(Qt.Orientation.Horizontal)
        self.ww_slider.setRange(1, 16384)
        self.ww_slider.setValue(2000)
        ag.addWidget(self.ww_slider)

        # Connect sliders
        self.wc_slider.valueChanged.connect(
            lambda v: (self.wc_val_lbl.setText(str(v)), self._emit_wl())
        )
        self.ww_slider.valueChanged.connect(
            lambda v: (self.ww_val_lbl.setText(str(v)), self._emit_wl())
        )

        ag.addWidget(_sep())

        # Export NIfTI
        self.export_nifti_btn = QPushButton("Save anonymised NIfTI …")
        self.export_nifti_btn.setObjectName("accent")
        self.export_nifti_btn.setEnabled(False)
        self.export_nifti_btn.clicked.connect(self.export_nifti_req)
        ag.addWidget(self.export_nifti_btn)

        grp.setLayout(ag)
        return grp

    # ── EXACT group ───────────────────────────────────────────────────────────

    def _build_exact_group(self) -> QGroupBox:
        grp = QGroupBox("EXACT Export")
        eg  = QVBoxLayout()
        eg.setSpacing(6)

        eg.addWidget(QLabel("Server URL:"))
        self.server_edit = QLineEdit()
        self.server_edit.setPlaceholderText("https://exact.yourinstitution.org")
        eg.addWidget(self.server_edit)

        # Auth mode selector
        auth_row = QHBoxLayout()
        self.radio_token = QRadioButton("API Token")
        self.radio_user  = QRadioButton("Username / Password")
        self.radio_token.setChecked(True)
        grp_btn = QButtonGroup(self)
        grp_btn.addButton(self.radio_token)
        grp_btn.addButton(self.radio_user)
        auth_row.addWidget(self.radio_token)
        auth_row.addWidget(self.radio_user)
        eg.addLayout(auth_row)

        # Stacked widget: page 0 = token, page 1 = user/pass
        self.auth_stack = QStackedWidget()

        # Page 0 — token
        token_page = QWidget()
        tp = QVBoxLayout(token_page)
        tp.setContentsMargins(0, 0, 0, 0)
        tp.setSpacing(4)
        tp.addWidget(QLabel("API Token:"))
        self.token_edit = QLineEdit()
        self.token_edit.setPlaceholderText("Paste your token here")
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        tp.addWidget(self.token_edit)
        self.save_token_check = QCheckBox("Remember token")
        tp.addWidget(self.save_token_check)
        self.auth_stack.addWidget(token_page)

        # Page 1 — username / password
        up_page = QWidget()
        up = QVBoxLayout(up_page)
        up.setContentsMargins(0, 0, 0, 0)
        up.setSpacing(4)
        up.addWidget(QLabel("Username:"))
        self.username_edit = QLineEdit()
        up.addWidget(self.username_edit)
        up.addWidget(QLabel("Password:"))
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        up.addWidget(self.password_edit)
        self.auth_stack.addWidget(up_page)

        self.radio_token.toggled.connect(
            lambda checked: self.auth_stack.setCurrentIndex(0 if checked else 1)
        )

        eg.addWidget(self.auth_stack)

        # Connect button
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.connect_req)
        eg.addWidget(self.connect_btn)

        eg.addWidget(_sep())

        eg.addWidget(QLabel("Image Set:"))
        self.imageset_combo = QComboBox()
        self.imageset_combo.setEnabled(False)
        self.imageset_combo.setPlaceholderText("— connect first —")
        eg.addWidget(self.imageset_combo)

        self.export_exact_btn = QPushButton("Upload to EXACT")
        self.export_exact_btn.setObjectName("accent")
        self.export_exact_btn.setEnabled(False)
        self.export_exact_btn.clicked.connect(self.export_exact_req)
        eg.addWidget(self.export_exact_btn)

        grp.setLayout(eg)
        return grp

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _emit_wl(self) -> None:
        self.wl_changed.emit(float(self.wc_slider.value()), float(self.ww_slider.value()))

    def set_wl_defaults(self, wc: float, ww: float) -> None:
        data_range = ww * 2
        self.wc_slider.blockSignals(True)
        self.ww_slider.blockSignals(True)
        self.wc_slider.setRange(int(wc - data_range), int(wc + data_range))
        self.ww_slider.setRange(1, int(data_range * 4) or 16384)
        self.wc_slider.setValue(int(wc))
        self.ww_slider.setValue(int(ww))
        self.wc_val_lbl.setText(str(int(wc)))
        self.ww_val_lbl.setText(str(int(ww)))
        self.wc_slider.blockSignals(False)
        self.ww_slider.blockSignals(False)

    def set_loaded(self, patient_name: str, patient_id: str) -> None:
        self.orig_name_lbl.setText(patient_name)
        self.export_nifti_btn.setEnabled(True)
        self.copy_btn.setEnabled(True)

    def set_connected(self, image_sets: list[dict]) -> None:
        self.imageset_combo.clear()
        for s in image_sets:
            label = f"{s.get('name', 'Unnamed')}  (id {s.get('id', '?')})"
            self.imageset_combo.addItem(label, userData=s.get("id"))
        self.imageset_combo.setEnabled(True)
        self.export_exact_btn.setEnabled(True)

    def selected_image_set_id(self) -> int | None:
        idx = self.imageset_combo.currentIndex()
        if idx < 0:
            return None
        return self.imageset_combo.itemData(idx)


# ── Worker threads ────────────────────────────────────────────────────────────

class _ScanWorker(QThread):
    """Quickly read DICOM headers to discover which series are present."""
    done  = pyqtSignal(list)   # list of series dicts from utils.scan_dicom_folder
    error = pyqtSignal(str)

    def __init__(self, path: str) -> None:
        super().__init__()
        self._path = path

    def run(self) -> None:
        try:
            series = utils.scan_dicom_folder(self._path)
            self.done.emit(series)
        except Exception as exc:
            self.error.emit(str(exc))


class _LoadWorker(QThread):
    done  = pyqtSignal(object, object, object)
    error = pyqtSignal(str)

    def __init__(self, path: str, series_uid: str | None = None) -> None:
        super().__init__()
        self._path       = path
        self._series_uid = series_uid

    def run(self) -> None:
        try:
            volume, datasets, meta = utils.load_dicom_series(
                self._path, self._series_uid
            )
            self.done.emit(volume, datasets, meta)
        except Exception as exc:
            self.error.emit('Error in _LoadWorker: ' + str(exc))


class _ExportWorker(QThread):
    done  = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, datasets, output_path: str, pseudonym: str) -> None:
        super().__init__()
        self._datasets = datasets
        self._output   = output_path
        self._name     = pseudonym

    def run(self) -> None:
        try:
            utils.export_nifti(self._datasets, self._output, self._name)
            self.done.emit(self._output)
        except Exception as exc:
            self.error.emit('Error in _ExportWorker'+str(exc))


class _ConnectWorker(QThread):
    done  = pyqtSignal(list, str)   # (image_sets, token)
    error = pyqtSignal(str)

    def __init__(self, client: ec.ExactClient, use_token: bool,
                 token: str, username: str, password: str) -> None:
        super().__init__()
        self._client    = client
        self._use_token = use_token
        self._token     = token
        self._username  = username
        self._password  = password

    def run(self) -> None:
        try:
            client = self._client
            if self._use_token:
                client.set_token(self._token)
            else:
                client.authenticate(self._username, self._password)
            client.verify_connection()
            image_sets = client.get_image_sets()
            self.done.emit(image_sets, client.token or "")
        except Exception as exc:
            self.error.emit(str(exc))


class _UploadWorker(QThread):
    done  = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, client: ec.ExactClient, image_set_id: int,
                 file_path: str, name: str) -> None:
        super().__init__()
        self._client       = client
        self._image_set_id = image_set_id
        self._file_path    = file_path
        self._name         = name

    def run(self) -> None:
        try:
            result = self._client.upload_image(
                self._image_set_id, self._file_path, self._name
            )
            self.done.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


# ── Series picker dialog ──────────────────────────────────────────────────────

class _SeriesPickerDialog(QDialog):
    """Modal dialog shown when a folder contains more than one DICOM series."""

    def __init__(self, series_list: list[dict], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select DICOM Series")
        self.setModal(True)
        self.resize(660, 280)
        self._series = series_list

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        lbl = QLabel(
            f"<b>{len(series_list)} series</b> found in this folder — "
            "select one to load:"
        )
        lbl.setStyleSheet("color:#d8ddf0;font-size:13px;padding-bottom:4px;")
        layout.addWidget(lbl)

        self._table = QTableWidget(len(series_list), 4)
        self._table.setHorizontalHeaderLabels(
            ["Series Description", "Modality", "Slices", "Image Size"]
        )
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft
        )
        self._table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(
            "QTableWidget{background:#1a1e30;alternate-background-color:#1e2340;"
            "gridline-color:#252a42;color:#d8ddf0;}"
            "QTableWidget::item:selected{background:#2d52c0;}"
            "QHeaderView::section{background:#1e2340;color:#7fa8ff;"
            "font-weight:700;font-size:11px;padding:4px;border:none;"
            "border-bottom:1px solid #252a42;}"
        )

        for row, s in enumerate(series_list):
            desc = s.get("description", "") or "(no description)"
            self._table.setItem(row, 0, QTableWidgetItem(desc))
            self._table.setItem(row, 1, QTableWidgetItem(s.get("modality", "")))
            self._table.setItem(row, 2, QTableWidgetItem(str(s.get("n_slices", "?"))))
            size = f"{s.get('rows', '?')} × {s.get('cols', '?')}"
            self._table.setItem(row, 3, QTableWidgetItem(size))

        self._table.selectRow(0)
        self._table.doubleClicked.connect(self.accept)
        layout.addWidget(self._table)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Load Selected")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def selected_uid(self) -> str | None:
        row = self._table.currentRow()
        return self._series[row]["uid"] if row >= 0 else None


# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DICOM Anonymizer")
        self.resize(1300, 780)

        self._datasets:  list | None = None
        self._meta:      dict        = {}
        self._last_nifti: str        = ""
        self._exact_client = ec.ExactClient()
        self._settings  = QSettings("DicomAnonymizer", "DicomAnonymizer")
        self._workers: list[QThread] = []  # keep references alive

        self._build_ui()
        self._restore_settings()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self._build_toolbar()

        # ── central layout ────────────────────────────────────────────────────
        central = QWidget()
        self.setCentralWidget(central)
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        # Left panel
        self._left = _LeftPanel()
        h.addWidget(self._left)

        # Thin divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.VLine)
        div.setStyleSheet("background:#1e2235;max-width:1px;")
        h.addWidget(div)

        # Viewer (centre, stretches)
        self._viewer = DicomViewer()
        self._viewer.setMinimumWidth(300)
        h.addWidget(self._viewer, stretch=1)

        # Thin divider
        div2 = QFrame()
        div2.setFrameShape(QFrame.Shape.VLine)
        div2.setStyleSheet("background:#1e2235;max-width:1px;")
        h.addWidget(div2)

        # Right panel
        self._right = _RightPanel()
        h.addWidget(self._right)

        # ── connections ───────────────────────────────────────────────────────
        self._right.wl_changed.connect(
            lambda wc, ww: self._viewer.set_wl(wc, ww)
        )
        self._right.export_nifti_req.connect(self._export_nifti)
        self._right.connect_req.connect(self._connect_exact)
        self._right.export_exact_req.connect(self._export_exact)
        self._right.gen_btn.clicked.connect(self._generate_name)
        self._right.copy_btn.clicked.connect(self._copy_pseudonym)
        self._right.pseudo_edit.textChanged.connect(
            lambda t: self._right.copy_btn.setEnabled(bool(t))
        )

        # Status bar
        self.statusBar().showMessage("Ready — open a DICOM file or directory to begin.")

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)

        open_file = QAction("Open DICOM File …", self)
        open_file.setShortcut("Ctrl+O")
        open_file.triggered.connect(self._open_file)
        tb.addAction(open_file)

        open_dir = QAction("Open DICOM Folder …", self)
        open_dir.setShortcut("Ctrl+Shift+O")
        open_dir.triggered.connect(self._open_dir)
        tb.addAction(open_dir)

        tb.addSeparator()

        about = QAction("About", self)
        about.triggered.connect(self._about)
        tb.addAction(about)

    # ── File loading ──────────────────────────────────────────────────────────

    def _open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open DICOM File", "",
            "DICOM files (*.dcm *.DCM *.ima *.IMA);;All files (*)"
        )
        if path:
            self._load_path(path)

    def _open_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open DICOM Folder")
        if path:
            self._load_path(path)

    def _load_path(self, path: str) -> None:
        self._viewer.clear()
        if Path(path).is_dir():
            self.statusBar().showMessage(f"Scanning {path} …")
            scanner = _ScanWorker(path)
            scanner.done.connect(lambda series: self._on_scanned(path, series))
            scanner.error.connect(self._on_load_error)
            self._workers.append(scanner)
            scanner.start()
        else:
            self._start_load(path, series_uid=None)

    def _on_scanned(self, path: str, series: list[dict]) -> None:
        if len(series) <= 1:
            uid = series[0]["uid"] if series else None
            self._start_load(path, uid)
        else:
            dlg = _SeriesPickerDialog(series, parent=self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                self.statusBar().showMessage("Load cancelled.")
                return
            self._start_load(path, dlg.selected_uid())

    def _start_load(self, path: str, series_uid: str | None) -> None:
        self.statusBar().showMessage(f"Loading {path} …")
        worker = _LoadWorker(path, series_uid)
        worker.done.connect(self._on_loaded)
        worker.error.connect(self._on_load_error)
        self._workers.append(worker)
        worker.start()

    def _on_loaded(self, volume, datasets, meta) -> None:
        self._datasets = datasets
        self._meta     = meta
        self._left.update(meta)
        self._viewer.load_volume(volume, meta["window_center"], meta["window_width"])
        self._right.set_wl_defaults(meta["window_center"], meta["window_width"])
        self._right.set_loaded(meta["patient_name"], meta["patient_id"])

        # Auto-populate pseudonym
        det = self._right.det_check.isChecked()
        seed = meta["patient_id"] if det else None
        self._right.pseudo_edit.setText(utils.generate_name(seed))

        n = meta.get("n_slices", "?")
        sh = meta.get("volume_shape", ())
        shape_str = f"{sh[2]}×{sh[1]}×{sh[0]}" if len(sh) == 3 else str(sh)
        self.statusBar().showMessage(
            f"Loaded {n} slices  —  {shape_str}  |  "
            f"{meta.get('modality', '')}  {meta.get('study_date', '')}"
        )

    def _on_load_error(self, msg: str) -> None:
        print('Showing message: ',msg)
        self.statusBar().showMessage("Load failed.")
        QMessageBox.critical(self, "DICOM Load Error", msg)

    # ── Pseudonym helpers ─────────────────────────────────────────────────────

    def _generate_name(self) -> None:
        det = self._right.det_check.isChecked()
        seed = self._meta.get("patient_id") if det else None
        name = utils.generate_name(seed)
        self._right.pseudo_edit.setText(name)

    def _copy_pseudonym(self) -> None:
        text = self._right.pseudo_edit.text().strip()
        if text:
            QGuiApplication.clipboard().setText(text)
            self.statusBar().showMessage(f'Copied "{text}" to clipboard.')

    # ── NIfTI export ──────────────────────────────────────────────────────────

    def _export_nifti(self) -> None:
        if not self._datasets:
            return
        pseudo = self._right.pseudo_edit.text().strip()
        if not pseudo:
            QMessageBox.warning(self, "No Pseudonym",
                                "Please enter or generate a pseudonym before exporting.")
            return

        suggested = f"{pseudo}.nii.gz"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save anonymised NIfTI", suggested,
            "NIfTI compressed (*.nii.gz);;NIfTI (*.nii)"
        )
        if not path:
            return

        self.statusBar().showMessage("Exporting NIfTI …")
        worker = _ExportWorker(self._datasets, path, pseudo)
        worker.done.connect(self._on_nifti_done)
        worker.error.connect(self._on_export_error)
        self._workers.append(worker)
        worker.start()

    def _on_nifti_done(self, path: str) -> None:
        self._last_nifti = path
        self.statusBar().showMessage(f"Saved: {path}")
        QMessageBox.information(self, "Export Complete",
                                f"Anonymised NIfTI saved to:\n{path}")

    def _on_export_error(self, msg: str) -> None:
        self.statusBar().showMessage("Export failed.")
        QMessageBox.critical(self, "Export Error", msg)

    # ── EXACT connection ──────────────────────────────────────────────────────

    def _connect_exact(self) -> None:
        server = self._right.server_edit.text().strip()
        if not server:
            QMessageBox.warning(self, "No Server", "Please enter the EXACT server URL.")
            return

        self._exact_client.set_base_url(server)
        use_token = self._right.radio_token.isChecked()
        token    = self._right.token_edit.text().strip()
        username = self._right.username_edit.text().strip()
        password = self._right.password_edit.text()

        if use_token and not token:
            QMessageBox.warning(self, "No Token", "Please paste your API token.")
            return
        if not use_token and not username:
            QMessageBox.warning(self, "No Credentials", "Please enter username and password.")
            return

        self._right.connect_btn.setEnabled(False)
        self.statusBar().showMessage("Connecting to EXACT …")

        worker = _ConnectWorker(self._exact_client, use_token, token, username, password)
        worker.done.connect(self._on_connected)
        worker.error.connect(self._on_connect_error)
        self._workers.append(worker)
        worker.start()

    def _on_connected(self, image_sets: list, token: str) -> None:
        self._right.connect_btn.setEnabled(True)
        self._right.set_connected(image_sets)
        self.statusBar().showMessage(
            f"Connected — {len(image_sets)} image set(s) available."
        )
        # Persist settings
        server = self._right.server_edit.text().strip()
        self._settings.setValue("exact/server", server)
        if self._right.save_token_check.isChecked() and token:
            self._settings.setValue("exact/token", token)
        else:
            self._settings.remove("exact/token")

    def _on_connect_error(self, msg: str) -> None:
        self._right.connect_btn.setEnabled(True)
        self.statusBar().showMessage("Connection failed.")
        QMessageBox.critical(self, "Connection Error",
                             f"Could not connect to EXACT:\n{msg}")

    # ── EXACT upload ──────────────────────────────────────────────────────────

    def _export_exact(self) -> None:
        if not self._datasets:
            QMessageBox.warning(self, "No DICOM", "Load a DICOM series first.")
            return

        image_set_id = self._right.selected_image_set_id()
        if image_set_id is None:
            QMessageBox.warning(self, "No Image Set", "Select an image set first.")
            return

        pseudo = self._right.pseudo_edit.text().strip()
        if not pseudo:
            QMessageBox.warning(self, "No Pseudonym", "Enter a pseudonym before uploading.")
            return

        # Use the already-saved NIfTI or create a temp one
        if self._last_nifti and Path(self._last_nifti).exists():
            nifti_path = self._last_nifti
            self._do_upload(nifti_path, image_set_id, pseudo)
        else:
            # Save to a temp file first, then upload
            tmp = tempfile.NamedTemporaryFile(
                suffix=".nii.gz", prefix=f"{pseudo}_", delete=False
            )
            tmp.close()
            self.statusBar().showMessage("Preparing NIfTI for upload …")
            worker = _ExportWorker(self._datasets, tmp.name, pseudo)
            worker.done.connect(
                lambda p: self._do_upload(p, image_set_id, pseudo)
            )
            worker.error.connect(self._on_export_error)
            self._workers.append(worker)
            worker.start()

    def _do_upload(self, nifti_path: str, image_set_id: int, pseudo: str) -> None:
        self.statusBar().showMessage("Uploading to EXACT …")
        self._right.export_exact_btn.setEnabled(False)
        name = f"{pseudo}.nii.gz"
        worker = _UploadWorker(self._exact_client, image_set_id, nifti_path, name)
        worker.done.connect(self._on_upload_done)
        worker.error.connect(self._on_upload_error)
        self._workers.append(worker)
        worker.start()

    def _on_upload_done(self, result: dict) -> None:
        self._right.export_exact_btn.setEnabled(True)
        self.statusBar().showMessage("Upload complete.")
        img_id = result.get("id", "?")
        QMessageBox.information(
            self, "Upload Complete",
            f"Image uploaded successfully (server id: {img_id})."
        )

    def _on_upload_error(self, msg: str) -> None:
        self._right.export_exact_btn.setEnabled(True)
        self.statusBar().showMessage("Upload failed.")
        QMessageBox.critical(self, "Upload Error", f"EXACT upload failed:\n{msg}")

    # ── Persistence ───────────────────────────────────────────────────────────

    def _restore_settings(self) -> None:
        server = self._settings.value("exact/server", "")
        token  = self._settings.value("exact/token",  "")
        if server:
            self._right.server_edit.setText(str(server))
        if token:
            self._right.token_edit.setText(str(token))
            self._right.save_token_check.setChecked(True)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._settings.sync()
        super().closeEvent(event)

    # ── About ─────────────────────────────────────────────────────────────────

    def _about(self) -> None:
        QMessageBox.about(
            self, "DICOM Anonymizer",
            "<b>DICOM Anonymizer</b><br>"
            "Load volumetric DICOM series, inspect them in three orthogonal views,<br>"
            "generate a pseudonym, and export an anonymised NIfTI file.<br><br>"
            "Optionally upload the result to an <b>EXACT</b> annotation server.<br><br>"
            "Scroll the mouse wheel over any view to step through slices.",
        )


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("DICOM Anonymizer")
    app.setApplicationVersion("1.0")
    app.setStyleSheet(STYLESHEET)

    font = QFont()
    font.setPointSize(12)
    app.setFont(font)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
