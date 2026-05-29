"""Core conversion logic: reshape flat frames into (T, Z, Y, X)."""

import logging
import numpy as np
import reader

logger = logging.getLogger(__name__)


def reshape_file_data(data, z_per_volume, t_per_file=None):
    """Reshape flat (N, H, W) to (T, Z, H, W).

    Assumes Z-fast, T-slow frame ordering.
    If the frame count is not an exact multiple of z_per_volume,
    trailing incomplete frames are dropped with a warning.

    Returns:
        (reshaped_data, actual_t_per_file)
    """
    n_frames, h, w = data.shape
    actual_t = n_frames // z_per_volume
    usable = actual_t * z_per_volume

    if actual_t == 0:
        raise ValueError(
            f"Need at least {z_per_volume} frames for one Z volume, "
            f"got only {n_frames}"
        )

    if n_frames != usable:
        logger.warning(
            f"Dropping {n_frames - usable} incomplete trailing frame(s) "
            f"(got {n_frames} frames, using {usable} = "
            f"{actual_t}T x {z_per_volume}Z)"
        )
        data = data[:usable]

    if t_per_file is not None and actual_t != t_per_file:
        logger.info(
            f"Expected {t_per_file} time points, got {actual_t} "
            f"({usable} frames / {z_per_volume}Z)"
        )

    return data.reshape(actual_t, z_per_volume, h, w), actual_t


class ConversionPlan:
    """Describes how input files map to output time points.

    Pre-scans all files on construction to compute the actual total
    time points, so that incomplete final files are handled gracefully.
    """

    def __init__(self, filepaths, z_per_volume, t_per_file=None, y_size=512, x_size=512, dtype="uint16"):
        self.filepaths = list(filepaths)
        self.z_per_volume = z_per_volume
        self.t_per_file = t_per_file  # None = auto-detect per file
        self.y_size = y_size
        self.x_size = x_size
        self.dtype = dtype

        # Pre-scan to compute actual time points per file
        self._file_actual_t = self._compute_actual_t()
        self.total_t = sum(self._file_actual_t)

        if self.total_t == 0:
            logger.warning("No usable time points found across all files")

        mode = "auto-detect" if t_per_file is None else f"{t_per_file}T fixed"
        logger.info(f"ConversionPlan: {len(filepaths)} file(s), "
                     f"{self.total_t} TP x {z_per_volume} Z ({mode}), "
                     f"{y_size}x{x_size}, {dtype}")

    def _compute_actual_t(self):
        """Pre-scan files to compute actual time points per file."""
        actual_t_list = []
        expected = self.z_per_volume * self.t_per_file if self.t_per_file else None
        for fp in self.filepaths:
            try:
                info = reader.read_tiff_info(fp)
                n_frames = info["n_frames"]
                actual_t = n_frames // self.z_per_volume
                remainder = n_frames % self.z_per_volume

                if actual_t == 0:
                    logger.warning(
                        f"File {fp} has only {n_frames} frames, "
                        f"less than z_per_volume={self.z_per_volume}; skipping"
                    )
                    actual_t_list.append(0)
                    continue

                # Warn if trailing incomplete frames (not a Z multiple)
                if remainder != 0:
                    logger.warning(
                        f"File {fp}: {n_frames} frames not a multiple of "
                        f"Z={self.z_per_volume}; dropping {remainder} trailing frame(s), "
                        f"using {actual_t}T"
                    )

                # Warn if fixed t_per_file constraint is violated
                if self.t_per_file is not None and actual_t != self.t_per_file:
                    logger.warning(
                        f"File {fp}: {n_frames} frames -> {actual_t}T "
                        f"(expected {self.t_per_file}T)"
                    )

                actual_t_list.append(actual_t)
            except Exception:
                logger.exception(f"Failed to read info for {fp}")
                actual_t_list.append(0)
        return actual_t_list

    @classmethod
    def from_directory(cls, directory, z_per_volume, t_per_file=None):
        """Create a plan by scanning a directory."""
        files = reader.scan_directory(directory)
        if not files:
            raise ValueError(f"No TIFF files found in {directory}")
        first_info = reader.read_tiff_info(files[0])
        return cls(
            filepaths=files,
            z_per_volume=z_per_volume,
            t_per_file=t_per_file,
            y_size=first_info["shape"][0],
            x_size=first_info["shape"][1],
            dtype=first_info["dtype"],
        )

    @property
    def shape(self):
        return (self.total_t, self.z_per_volume, self.y_size, self.x_size)

    def check_consistency(self):
        """Verify all files; warn on trailing incomplete frames or constraint violations.

        Uses pre-scanned values from _compute_actual_t().
        """
        expected = self.z_per_volume * self.t_per_file if self.t_per_file else None
        issues = []
        for fp, actual_t in zip(self.filepaths, self._file_actual_t):
            n_frames = actual_t * self.z_per_volume
            if actual_t == 0:
                issues.append((fp, 0))
                logger.warning(
                    f"Skipping file with insufficient frames: {fp}"
                )
            elif self.t_per_file is not None and actual_t != self.t_per_file:
                issues.append((fp, n_frames))
                logger.warning(
                    f"Frame count mismatch: {fp} has "
                    f"{n_frames}, expected {expected}"
                )
        return issues

    def iter_timepoints(self):
        """Generator yielding (global_t_index, z_stack) for each time point.

        Handles files with fewer time points than expected by using
        the pre-scanned actual time point counts.
        """
        global_t_start = 0
        for file_idx, (fpath, actual_t) in enumerate(
                zip(self.filepaths, self._file_actual_t)):
            if actual_t == 0:
                logger.warning(
                    f"Skipping file {file_idx + 1}/{len(self.filepaths)} "
                    f"(insufficient frames): {fpath}"
                )
                continue

            logger.info(
                f"Reading file {file_idx + 1}/{len(self.filepaths)}: {fpath}"
                f" (expecting {actual_t}T)"
            )
            try:
                data = reader.read_tiff_full(fpath)
            except Exception:
                logger.exception(f"Failed to read {fpath}")
                raise

            try:
                reshaped, t_from_data = reshape_file_data(
                    data, self.z_per_volume, actual_t)
            except ValueError as e:
                logger.error(f"Reshape failed for {fpath}: {e}")
                raise ValueError(f"File {fpath}: {e}")

            for local_t in range(t_from_data):
                global_t = global_t_start + local_t
                yield global_t, reshaped[local_t]

            global_t_start += t_from_data
