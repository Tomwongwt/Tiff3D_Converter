"""IMS (Imaris) writer via ImarisConvertBioformats CLI."""

import logging
import subprocess
import os
import shutil
import tempfile
import numpy as np
import tifffile

logger = logging.getLogger(__name__)

# Default system install path
_IMARIS_DEFAULT = (
    r"C:\Program Files\Bitplane\ImarisConvertBioformats 11.0.1"
    r"\ImarisConvertBioformats.exe"
)


def _find_imaris_convert():
    """Find ImarisConvertBioformats.exe. Checks:
    1. Bundled path relative to this script/exe
    2. System install path
    """
    # Check alongside the script/exe (bundled)
    import sys
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))

    bundled = os.path.join(base, "ImarisConvertBioformats", "ImarisConvertBioformats.exe")
    if os.path.isfile(bundled):
        logger.info(f"Using bundled ImarisConvertBioformats: {bundled}")
        return bundled

    if os.path.isfile(_IMARIS_DEFAULT):
        logger.info(f"Using system ImarisConvertBioformats: {_IMARIS_DEFAULT}")
        return _IMARIS_DEFAULT

    return None


def write_ims(
    filepath,
    shape,
    dtype,
    iter_timepoints,
    xy_pixel_um=1.0,
    z_step_um=2.0,
    progress_callback=None,
):
    """Write IMS via individual TIFFs + ImarisConvertBioformats CLI."""
    imaris_exe = _find_imaris_convert()
    if not imaris_exe:
        raise RuntimeError(
            "ImarisConvertBioformats not found.\n"
            "Please install Imaris or ensure ImarisConvertBioformats is bundled."
        )

    total_t, z_size, y_size, x_size = shape
    total_files = total_t * z_size
    logger.info(f"IMS write: {filepath} ({total_t}T x {z_size}Z x {y_size}x{x_size})")

    if progress_callback:
        progress_callback(0, total_files, "Writing individual TIFFs...")

    tmp_dir = tempfile.mkdtemp()
    first_file = None
    written = 0

    try:
        for global_t, z_stack in iter_timepoints:
            for z_idx in range(z_size):
                try:
                    frame = np.asarray(z_stack[z_idx], dtype=np.uint16)
                    fname = f"img_T{global_t:04d}_Z{z_idx:04d}.tif"
                    fpath = os.path.join(tmp_dir, fname)
                    tifffile.imwrite(fpath, frame)
                except Exception:
                    logger.exception(f"Failed to write {fname}")
                    raise

                if first_file is None:
                    first_file = fpath
                written += 1

                if progress_callback and written % 10 == 0:
                    progress_callback(written, total_files,
                                      f"Writing TIFFs ({written}/{total_files})...")

        logger.info(f"  Wrote {written} TIFFs to {tmp_dir}")

        if progress_callback:
            progress_callback(total_files, total_files,
                              "Converting to IMS (ImarisConvertBioformats)...")

        cmd = [
            imaris_exe,

            "-i", first_file,
            "-o", filepath,
            "--voxelsizex", str(xy_pixel_um),
            "--voxelsizey", str(xy_pixel_um),
            "--voxelsizez", str(z_step_um),
        ]
        logger.info(f"  Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        except subprocess.TimeoutExpired:
            logger.error("ImarisConvertBioformats timed out after 600s")
            raise RuntimeError("ImarisConvertBioformats timed out after 600 seconds")
        except FileNotFoundError:
            logger.error(f"ImarisConvertBioformats executable not found: {IMARIS_CONVERT}")
            raise

        if result.returncode != 0:
            error_msg = (result.stderr or result.stdout or "(no output)").strip()
            logger.error(f"ImarisConvertBioformats failed (rc={result.returncode}): {error_msg[:200]}")
            raise RuntimeError(
                f"ImarisConvertBioformats failed (exit code {result.returncode}):\n"
                f"Output: {error_msg[:500]}"
            )

        logger.info(f"  IMS written successfully: {filepath}")

    finally:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            logger.debug(f"  Cleaned up temp dir: {tmp_dir}")
        except Exception:
            pass

    if progress_callback:
        progress_callback(total_files, total_files, "Done!")
