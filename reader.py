"""BigTIFF reader for ScanImage 3D+time sequences."""

import logging
import tifffile
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)


def _to_uint16(data):
    """Convert int16 data to uint16: add 32768 so 0 maps to mid-range."""
    if data.dtype == np.int16:
        logger.debug("Converting int16 -> uint16 (+32768)")
        return (data.astype(np.int32) + 32768).clip(0, 65535).astype(np.uint16)
    return data


def read_tiff_info(filepath):
    """Return basic info about a TIFF file without loading all data."""
    logger.info(f"Reading info: {filepath}")
    try:
        with tifffile.TiffFile(filepath) as tf:
            n_frames = len(tf.pages)
            shape = tf.pages[0].shape
            dtype = tf.pages[0].dtype
            info = {
                "n_frames": n_frames,
                "shape": shape,
                "dtype": str(dtype),
                "filepath": str(filepath),
                "filesize_mb": Path(filepath).stat().st_size / (1024 * 1024),
            }
            logger.info(f"  {n_frames} frames, {shape}, {dtype}, {info['filesize_mb']:.1f} MB")
            return info
    except Exception:
        logger.exception(f"Failed to read TIFF info: {filepath}")
        raise


def read_tiff_frames(filepath, start=0, count=None):
    """Read a range of frames from a TIFF file."""
    logger.debug(f"Reading frames [{start}:{start + count if count else 'end'}] from {filepath}")
    try:
        with tifffile.TiffFile(filepath) as tf:
            if count is None:
                count = len(tf.pages) - start
            frames = np.empty((count, *tf.pages[0].shape), dtype=tf.pages[0].dtype)
            for i in range(count):
                frames[i] = tf.pages[start + i].asarray()
            return _to_uint16(frames)
    except Exception:
        logger.exception(f"Failed to read frames from {filepath}")
        raise


def read_tiff_full(filepath):
    """Read entire TIFF file into memory."""
    logger.info(f"Reading full TIFF: {filepath}")
    try:
        with tifffile.TiffFile(filepath) as tf:
            n = len(tf.pages)
            shape = (n, *tf.pages[0].shape)
            data = np.empty(shape, dtype=tf.pages[0].dtype)
            for i in range(n):
                data[i] = tf.pages[i].asarray()
            logger.info(f"  Read {n} frames, dtype={data.dtype}")
            return _to_uint16(data)
    except Exception:
        logger.exception(f"Failed to read full TIFF: {filepath}")
        raise


def parse_scanimage_metadata(filepath):
    """Extract key ScanImage parameters from TIFF metadata."""
    logger.debug(f"Parsing ScanImage metadata: {filepath}")
    si_keys = [
        ("numFramesPerVolume", "si_frames_per_volume"),
        ("numSlices", "si_slices"),
        ("stackZStepSize", "si_z_step_um"),
        ("framesPerSlice", "si_frames_per_slice"),
        ("numVolumes", "si_volumes"),
        ("logAverageFactor", "si_log_average"),
    ]

    info = {}
    try:
        with tifffile.TiffFile(filepath) as tf:
            page0 = tf.pages[0]

            text_sources = []
            if hasattr(page0, "description") and page0.description:
                desc = page0.description
                if isinstance(desc, bytes):
                    desc = desc.decode("latin-1", errors="replace")
                text_sources.append(desc)
            if hasattr(page0, "software") and page0.software:
                sw = page0.software
                if isinstance(sw, bytes):
                    sw = sw.decode("latin-1", errors="replace")
                text_sources.append(sw)

            for text in text_sources:
                for line in text.split("\n"):
                    if "=" in line:
                        key, _, val = line.partition("=")
                        key = key.strip()
                        val = val.strip()
                        for suffix, info_key in si_keys:
                            if key.endswith(suffix):
                                try:
                                    info[info_key] = int(val)
                                except ValueError:
                                    try:
                                        info[info_key] = float(val)
                                    except ValueError:
                                        pass

        logger.info(f"  ScanImage params: slices={info.get('si_slices')}, "
                     f"z_step={info.get('si_z_step_um')}um, "
                     f"frames_per_slice={info.get('si_frames_per_slice')}")
    except Exception:
        logger.warning(f"Could not parse ScanImage metadata from {filepath}", exc_info=True)

    return info


def scan_directory(directory):
    """List all TIFF files in directory, sorted by name."""
    logger.info(f"Scanning directory: {directory}")
    try:
        d = Path(directory)
        tiffs = sorted(d.glob("*.tif")) + sorted(d.glob("*.tiff"))
        logger.info(f"  Found {len(tiffs)} TIFF file(s)")
        return [str(t) for t in tiffs]
    except Exception:
        logger.exception(f"Failed to scan directory: {directory}")
        raise
