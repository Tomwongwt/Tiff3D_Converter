"""TIFF writer — OME-TIFF, 2D series, pure stack."""

import logging
import os
import numpy as np
import tifffile

logger = logging.getLogger(__name__)


def write_ome_tiff(
    filepath,
    shape,
    dtype,
    iter_timepoints,
    xy_pixel_um=1.0,
    z_step_um=2.0,
    progress_callback=None,
):
    """Write a single OME-TIFF with full (T, Z, Y, X) structure and metadata."""
    total_t, z_size, y_size, x_size = shape
    total_pages = total_t * z_size
    logger.info(f"OME-TIFF write: {filepath} ({total_t}T x {z_size}Z x {y_size}x{x_size})")

    if progress_callback:
        progress_callback(0, total_pages, "Collecting data...")

    try:
        data_4d = np.empty(shape, dtype=dtype)
        for global_t, z_stack in iter_timepoints:
            data_4d[global_t] = z_stack
            if progress_callback:
                progress_callback(global_t + 1, total_t, "Collecting data...")

        data_4d = np.asarray(data_4d, dtype=np.uint16)

        if progress_callback:
            progress_callback(0, 1, "Writing OME-TIFF...")

        data_bytes = data_4d.nbytes
        need_bigtiff = data_bytes > 4 * 1024 * 1024 * 1024
        logger.info(f"  Data size: {data_bytes / 1024**3:.2f} GB, BigTIFF={need_bigtiff}")

        tifffile.imwrite(
            filepath,
            data_4d,
            bigtiff=need_bigtiff,
            ome=True,
            metadata={
                "axes": "TZYX",
                "PhysicalSizeX": xy_pixel_um,
                "PhysicalSizeXUnit": "um",
                "PhysicalSizeY": xy_pixel_um,
                "PhysicalSizeYUnit": "um",
                "PhysicalSizeZ": z_step_um,
                "PhysicalSizeZUnit": "um",
            },
        )
        logger.info(f"  Written: {filepath}")
    except Exception:
        logger.exception(f"Failed to write OME-TIFF: {filepath}")
        raise

    if progress_callback:
        progress_callback(total_pages, total_pages, "Done!")


def write_pure_stack(
    filepath,
    shape,
    dtype,
    iter_timepoints,
    progress_callback=None,
):
    """Write a single multi-page TIFF with all frames (Z-fast, T-slow)."""
    total_t, z_size, y_size, x_size = shape
    total_pages = total_t * z_size
    data_bytes = total_pages * y_size * x_size * 2
    need_bigtiff = data_bytes > 4 * 1024 * 1024 * 1024
    logger.info(f"Pure stack write: {filepath} ({total_pages} pages, BigTIFF={need_bigtiff})")

    try:
        with tifffile.TiffWriter(filepath, bigtiff=need_bigtiff) as tif:
            page_idx = 0
            for global_t, z_stack in iter_timepoints:
                for z_idx in range(z_size):
                    frame = np.asarray(z_stack[z_idx], dtype=np.uint16)
                    tif.write(frame, contiguous=True)
                    page_idx += 1
                    if progress_callback and page_idx % 10 == 0:
                        progress_callback(page_idx, total_pages,
                                          f"Writing frames ({page_idx}/{total_pages})...")
        logger.info(f"  Written: {filepath}")
    except Exception:
        logger.exception(f"Failed to write pure stack: {filepath}")
        raise

    if progress_callback:
        progress_callback(total_pages, total_pages,
                          f"Done! {total_pages} frames in {filepath}")


def write_2d_series(
    output_dir,
    name_prefix,
    shape,
    dtype,
    iter_timepoints,
    progress_callback=None,
):
    """Write individual 2D TIFF files for each (T, Z) combination."""
    total_t, z_size, y_size, x_size = shape
    total_files = total_t * z_size
    logger.info(f"2D series write: {output_dir}/ ({total_files} files)")

    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as e:
        logger.error(f"Cannot create output directory: {output_dir}: {e}")
        raise

    written = 0
    try:
        for global_t, z_stack in iter_timepoints:
            for z_idx in range(z_size):
                try:
                    frame = np.asarray(z_stack[z_idx], dtype=np.uint16)
                    fname = f"{name_prefix}_T{global_t:04d}_Z{z_idx:04d}.tif"
                    fpath = os.path.join(output_dir, fname)
                    tifffile.imwrite(fpath, frame)
                except Exception:
                    logger.exception(f"Failed to write {fname}")
                    raise
                written += 1

                if progress_callback and written % 10 == 0:
                    progress_callback(written, total_files,
                                      f"Writing 2D TIFFs ({written}/{total_files})...")
        logger.info(f"  Written {written} files")
    except Exception:
        logger.exception(f"Failed during 2D series write after {written}/{total_files} files")
        raise

    if progress_callback:
        progress_callback(written, total_files,
                          f"Done! {written} files written.")

    return written
