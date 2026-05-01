"""DICOM loading, NIfTI export, and pseudonym generation."""

from __future__ import annotations
import hashlib
import random
from pathlib import Path

import numpy as np
import pydicom
import nibabel as nib

# ── Pseudonym generation ──────────────────────────────────────────────────────

_ADJECTIVES = [
    "Swift", "Calm", "Bold", "Clear", "Bright", "Silent", "Sharp", "Deep",
    "Free", "Keen", "Pure", "Quiet", "Wise", "Cool", "Fair", "Kind",
    "Safe", "Soft", "Wild", "Warm", "Brave", "Fresh", "Grand", "Lean",
    "Mild", "Neat", "Rich", "Slim", "Strong", "Tall", "Wide", "Dark",
    "Smooth", "Stern", "Noble", "Brisk", "Crisp", "Fleet", "Stout", "Tidy",
]

_NOUNS = [
    "River", "Stone", "Cedar", "Maple", "Falcon", "Harbor", "Meadow",
    "Summit", "Ridge", "Valley", "Brook", "Forest", "Garden", "Grove",
    "Hill", "Lake", "Ocean", "Peak", "Plain", "Shore", "Spring", "Stream",
    "Tide", "Trail", "Wave", "Wood", "Canyon", "Cliff", "Coast", "Crest",
    "Delta", "Glen", "Heath", "Inlet", "Isle", "Knoll", "Mesa", "Pass",
    "Pond", "Reef", "Sand", "Slope", "Dune", "Mound", "Birch", "Hazel",
]


def generate_name(seed: str | None = None) -> str:
    """Return a short pseudonym like 'SwiftRiver'.

    If seed is given the result is deterministic (same seed → same name).
    """
    if seed:
        h = int(hashlib.sha256(seed.encode()).hexdigest(), 16) % (2 ** 32)
        rng = random.Random(h)
    else:
        rng = random.Random()
    return rng.choice(_ADJECTIVES) + rng.choice(_NOUNS)


# ── DICOM loading ─────────────────────────────────────────────────────────────

def load_dicom_series(path: str | Path) -> tuple[np.ndarray, list, dict]:
    """Load a DICOM series from *path* (file or directory).

    Returns
    -------
    volume   : ndarray, shape (Z, Y, X), rescaled to int16 HU / signal units
    datasets : list of pydicom Datasets (one per slice, sorted)
    meta     : dict with display metadata and window/level defaults
    """
    path = Path(path)
    candidates: list[Path] = []
    if path.is_dir():
        for pat in ("*.dcm", "*.DCM", "*.ima", "*.IMA"):
            candidates.extend(sorted(path.rglob(pat)))
        if not candidates:
            candidates = [f for f in path.iterdir() if f.is_file()]
    else:
        candidates = [path]

    datasets: list = []
    for f in candidates:
        try:
            ds = pydicom.dcmread(str(f), force=True)
            _ = ds.pixel_array  # ensure pixel data is present
            datasets.append(ds)
        except Exception as e:
            print(str(e))
            continue

    if not datasets:
        raise ValueError(f"No valid DICOM files with pixel data found in: {path}")

    datasets.sort(key=_slice_sort_key)

    slices = [_apply_rescale(ds, ds.pixel_array) for ds in datasets]
    volume = np.stack(slices, axis=0)

    meta = _extract_metadata(datasets[0])
    meta["volume_shape"] = volume.shape
    meta["n_slices"] = volume.shape[0]

    # Window / level defaults from DICOM tags, fall back to data statistics
    ds0 = datasets[0]
    try:
        wc = float(ds0.WindowCenter[0] if hasattr(ds0.WindowCenter, "__iter__") else ds0.WindowCenter)
        ww = float(ds0.WindowWidth[0]  if hasattr(ds0.WindowWidth,  "__iter__") else ds0.WindowWidth)
    except (AttributeError, TypeError, ValueError):
        wc = float(np.percentile(volume, 50))
        ww = float(np.percentile(volume, 99) - np.percentile(volume, 1))
        ww = max(ww, 1.0)

    meta["window_center"] = wc
    meta["window_width"]  = ww
    meta["data_min"] = int(volume.min())
    meta["data_max"] = int(volume.max())

    return volume, datasets, meta


def _apply_rescale(ds, arr: np.ndarray) -> np.ndarray:
    slope = float(getattr(ds, "RescaleSlope", 1) or 1)
    intercept = float(getattr(ds, "RescaleIntercept", 0) or 0)
    if slope != 1.0 or intercept != 0.0:
        return (arr.astype(np.float32) * slope + intercept).astype(np.int16)
    return arr.astype(np.int16)


def _slice_sort_key(ds) -> float:
    try:
        return float(ds.ImagePositionPatient[2])
    except Exception:
        pass
    try:
        return float(ds.InstanceNumber)
    except Exception:
        return 0.0


def _extract_metadata(ds) -> dict:
    def sg(attr: str, default: str = "") -> str:
        v = getattr(ds, attr, None)
        return str(v).strip() if v is not None else default

    return {
        "patient_name":       sg("PatientName",       "Unknown"),
        "patient_id":         sg("PatientID",          "Unknown"),
        "patient_dob":        sg("PatientBirthDate",   ""),
        "patient_sex":        sg("PatientSex",         ""),
        "patient_age":        sg("PatientAge",         ""),
        "study_date":         sg("StudyDate",          ""),
        "study_description":  sg("StudyDescription",  ""),
        "series_description": sg("SeriesDescription", ""),
        "modality":           sg("Modality",           ""),
        "manufacturer":       sg("Manufacturer",       ""),
    }


# ── NIfTI export ──────────────────────────────────────────────────────────────

_ANON_TAGS = [
    (0x0010, 0x0010),  # PatientName
    (0x0010, 0x0020),  # PatientID
    (0x0010, 0x0030),  # PatientBirthDate
    (0x0010, 0x0040),  # PatientSex
    (0x0010, 0x1000),  # OtherPatientIDs
    (0x0010, 0x1001),  # OtherPatientNames
    (0x0010, 0x1010),  # PatientAge
    (0x0010, 0x1020),  # PatientSize
    (0x0010, 0x1030),  # PatientWeight
    (0x0008, 0x0080),  # InstitutionName
    (0x0008, 0x0081),  # InstitutionAddress
    (0x0008, 0x1070),  # OperatorsName
    (0x0008, 0x0090),  # ReferringPhysicianName
    (0x0010, 0x4000),  # PatientComments
    (0x0008, 0x1048),  # PhysiciansOfRecord
    (0x0032, 0x4000),  # StudyComments
]


def _build_affine(datasets: list) -> np.ndarray:
    """Construct a NIfTI affine from DICOM orientation/position tags."""
    ds = datasets[0]
    try:
        iop = [float(x) for x in ds.ImageOrientationPatient]
        ipp = [float(x) for x in ds.ImagePositionPatient]
        ps  = [float(x) for x in ds.PixelSpacing]

        row_cos  = np.array(iop[:3])
        col_cos  = np.array(iop[3:])
        normal   = np.cross(row_cos, col_cos)

        if len(datasets) > 1:
            ipp2    = [float(x) for x in datasets[1].ImagePositionPatient]
            spacing = float(np.linalg.norm(np.array(ipp2) - np.array(ipp)))
        else:
            spacing = float(getattr(ds, "SliceThickness", 1.0) or 1.0)

        affine = np.eye(4)
        affine[:3, 0] = row_cos * ps[1]   # column direction → X
        affine[:3, 1] = col_cos * ps[0]   # row direction    → Y
        affine[:3, 2] = normal  * spacing  # slice direction  → Z
        affine[:3, 3] = ipp
        return affine
    except Exception:
        return np.eye(4)


def export_nifti(datasets: list, output_path: str | Path, patient_name: str) -> Path:
    """Write an anonymized NIfTI-1 file from *datasets*.

    All identifying DICOM metadata is stripped; only the pseudonym is stored
    in the NIfTI description field.
    """
    volume = np.stack(
        [_apply_rescale(ds, ds.pixel_array) for ds in datasets], axis=2
    )  # shape (Y, X, Z) — NIfTI convention

    volume = np.transpose(volume,[1,0,2])

    affine = _build_affine(datasets)
    img    = nib.Nifti1Image(volume, affine)
    hdr    = img.header
    hdr.set_xyzt_units("mm", "sec")
    hdr["descrip"] = f"Anon:{patient_name}".encode()[:80]

    output_path = Path(output_path)
    nib.save(img, str(output_path))
    return output_path
