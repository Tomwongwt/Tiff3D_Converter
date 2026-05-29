[English](README.md) | [中文](README_zh.md)

# Tiff3D Converter

Convert 3D+Time TIFF sequences (typically from ScanImage microscopes) into OME-TIFF, IMS (Imaris), or 2D TIFF series.

© 2026 Tom Wong - Tsinghua University. Powered by DeepSeek & Claude Code.

## Features

- **GUI application** (Tkinter) for easy parameter configuration and preview
- Reads BigTIFF files produced by ScanImage (Z-fast, T-slow frame ordering)
- Auto-detects ScanImage metadata (Z slices, Z step) from TIFF headers
- Outputs three formats:
  - **OME-TIFF** — 4D (T,Z,Y,X) stack with OME-XML metadata, openable in Imaris
  - **IMS (.ims)** — Imaris native format via bundled `ImarisConvertBioformats`
  - **2D-TIFF Series** — individual `name_T####_Z####.tif` files per slice
- Handles incomplete final files gracefully — truncates to nearest Z multiple

## Requirements

- Python 3.8+
- `tifffile >= 2024.1`
- `numpy >= 1.24`

Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

### GUI

```bash
python tiff3d_gui.py
```

1. Select an **input folder** containing `.tif`/`.tiff` files
2. Configure **parameters**:
   - **Z slices per volume** — auto-detected from ScanImage metadata if available
   - **Time points per file** — number of volumes per TIFF file
   - **Z step (µm)** — voxel size in Z
   - **XY pixel size (µm)** — auto or manual
3. Choose an **output folder** and **output name**
4. Select **output format** (OME-TIFF / IMS / 2D-TIFF Series)
5. Click **Convert**

### Library

```python
import reader
import converter
import tiff2d_writer

# Build conversion plan
plan = converter.ConversionPlan.from_directory(
    "path/to/tiffs", z_per_volume=21, t_per_file=10
)

# Check for inconsistencies
issues = plan.check_consistency()

# Write OME-TIFF
tiff2d_writer.write_ome_tiff(
    "output.ome.tif",
    plan.shape,
    plan.dtype,
    plan.iter_timepoints(),
    xy_pixel_um=0.9,
    z_step_um=2.0,
)
```

## Output Formats

| Format | Extension | Description |
|---|---|---|
| OME-TIFF | `.ome.tif` | Single 4D BigTIFF with OME metadata, Imaris-compatible |
| IMS | `.ims` | Imaris native format (requires bundled `ImarisConvertBioformats`) |
| 2D-TIFF Series | `.tif` (per slice) | One file per (T,Z) — `name_T0000_Z0000.tif` |

## Frame Ordering

The converter assumes **Z-fast, T-slow** frame ordering (ScanImage default):

```
Frame 0: T0 Z0
Frame 1: T0 Z1
...
Frame Z-1: T0 Z(Z-1)
Frame Z: T1 Z0
...
```

## Incomplete Files

If the last TIFF file has fewer frames than expected (e.g., acquisition was stopped early), the converter:

- Truncates to the largest multiple of Z slices
- Drops trailing incomplete frames with a warning
- Skips files that have fewer frames than one full Z volume

No error is raised — the conversion proceeds with the available complete volumes.

## Build (Windows EXE)

Uses PyInstaller to create a standalone executable:

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name Tiff3D_Converter tiff3d_gui.py
```

Bundle `ImarisConvertBioformats` for IMS output support by placing it alongside the executable in `ImarisConvertBioformats/`.

## License

MIT License — see [LICENSE](LICENSE).

© 2026 Tom Wong - Tsinghua University. Powered by DeepSeek & Claude Code.
