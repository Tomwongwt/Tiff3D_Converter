"""GUI for 3D+Time TIFF -> IMS / OME-TIFF / 2D-TIFF Series Converter.

Usage: python tiff3d_gui.py
"""

import json
import logging
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

# ---- Config persistence ---------------------------------------------------

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(BASE_DIR, "config.json")


def _load_config():
    """Load saved settings from config.json."""
    try:
        if os.path.isfile(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_config(data):
    """Save settings to config.json."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

# ---- Logging ---------------------------------------------------------------

LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, f"converter_{datetime.now():%Y%m%d_%H%M%S}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("tiff3d_gui")

import reader
import converter
import ims_writer
import tiff2d_writer


class Tiff3dConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("3D TIFF -> OME-TIFF / IMS / 2D-TIFF Converter")
        self.root.geometry("720x680")
        self.root.resizable(True, True)

        self.source_files = []
        self._conversion_plan = None
        self._cfg = _load_config()
        self._build_ui()
        self._restore_state()
        self._update_preview()

        # Save config on close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        logger.info("GUI started")

    def _restore_state(self):
        """Restore last-used folders and settings from config."""
        cfg = self._cfg
        if cfg.get("input_dir") and os.path.isdir(cfg["input_dir"]):
            self.input_dir_var.set(cfg["input_dir"])
            self._refresh_file_list(restore=True)
        if cfg.get("output_dir"):
            self.out_dir_var.set(cfg["output_dir"])
        if cfg.get("format"):
            self.format_var.set(cfg["format"])
        if cfg.get("name"):
            self.name_var.set(cfg["name"])
        if cfg.get("z_slices"):
            self.z_var.set(cfg["z_slices"])
        if cfg.get("t_per_file"):
            self.t_var.set(cfg["t_per_file"])
        if cfg.get("z_step"):
            self.zstep_var.set(cfg["z_step"])

    def _save_state(self):
        """Persist current settings."""
        self._cfg.update({
            "input_dir": self.input_dir_var.get(),
            "output_dir": self.out_dir_var.get(),
            "format": self.format_var.get(),
            "name": self.name_var.get(),
        })
        try:
            self._cfg["z_slices"] = self.z_var.get()
            self._cfg["t_per_file"] = self.t_var.get()
            self._cfg["z_step"] = self.zstep_var.get()
        except tk.TclError:
            pass
        _save_config(self._cfg)

    def _on_close(self):
        self._save_state()
        self.root.destroy()

    # ---- UI construction --------------------------------------------------

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)
        self._build_input_section(main)
        self._build_params_section(main)
        self._build_output_section(main)
        self._build_preview_section(main)
        self._build_action_section(main)

    def _build_input_section(self, parent):
        frame = ttk.LabelFrame(parent, text="Input", padding=8)
        frame.pack(fill=tk.X, pady=(0, 8))

        row = ttk.Frame(frame)
        row.pack(fill=tk.X)
        ttk.Label(row, text="Source folder:").pack(side=tk.LEFT)
        self.input_dir_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.input_dir_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(row, text="Browse...", command=self._browse_input).pack(side=tk.LEFT)

        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_listbox = tk.Listbox(
            list_frame, selectmode=tk.EXTENDED,
            yscrollcommand=scrollbar.set, height=6)
        self.file_listbox.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.file_listbox.yview)

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(btn_row, text="Select All", command=self._select_all).pack(
            side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_row, text="Deselect All", command=self._deselect_all).pack(
            side=tk.LEFT)

    def _build_params_section(self, parent):
        frame = ttk.LabelFrame(parent, text="Parameters", padding=8)
        frame.pack(fill=tk.X, pady=(0, 8))

        self.z_var = tk.IntVar(value=21)
        self.t_var = tk.IntVar(value=10)
        self.zstep_var = tk.DoubleVar(value=2.0)
        self.xypix_var = tk.StringVar(value="auto")

        row1 = ttk.Frame(frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="Z slices per volume:").pack(side=tk.LEFT)
        ttk.Spinbox(row1, textvariable=self.z_var, from_=1, to=999, width=8).pack(
            side=tk.LEFT, padx=4)
        ttk.Label(row1, text="Time points per file:").pack(side=tk.LEFT, padx=(16, 0))
        ttk.Spinbox(row1, textvariable=self.t_var, from_=1, to=9999, width=8).pack(
            side=tk.LEFT, padx=4)

        row2 = ttk.Frame(frame)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="Z step (um):").pack(side=tk.LEFT)
        ttk.Entry(row2, textvariable=self.zstep_var, width=8).pack(side=tk.LEFT, padx=4)
        ttk.Label(row2, text="XY pixel size (um):").pack(side=tk.LEFT, padx=(16, 0))
        ttk.Entry(row2, textvariable=self.xypix_var, width=8).pack(side=tk.LEFT, padx=4)
        ttk.Label(row2, text="(auto=from metadata)").pack(side=tk.LEFT, padx=4)

        for var in (self.z_var, self.t_var, self.zstep_var):
            var.trace_add("write", lambda *_: self._update_preview())

    def _build_output_section(self, parent):
        frame = ttk.LabelFrame(parent, text="Output", padding=8)
        frame.pack(fill=tk.X, pady=(0, 8))

        row1 = ttk.Frame(frame)
        row1.pack(fill=tk.X)
        ttk.Label(row1, text="Output folder:").pack(side=tk.LEFT)
        self.out_dir_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self.out_dir_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(row1, text="Browse...", command=self._browse_output).pack(side=tk.LEFT)

        row2 = ttk.Frame(frame)
        row2.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(row2, text="Output name:").pack(side=tk.LEFT)
        self.name_var = tk.StringVar(value="converted")
        ttk.Entry(row2, textvariable=self.name_var, width=20).pack(side=tk.LEFT, padx=4)

        ttk.Label(row2, text="Format:").pack(side=tk.LEFT, padx=(16, 0))
        self.format_var = tk.StringVar(value="ome")
        self.format_var.trace_add("write", lambda *_: self._save_state())
        ttk.Radiobutton(row2, text="OME-TIFF (Imaris)", variable=self.format_var,
                        value="ome").pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(row2, text="2D-TIFF Series", variable=self.format_var,
                        value="series").pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(row2, text="IMS (.ims)", variable=self.format_var,
                        value="ims").pack(side=tk.LEFT, padx=4)

    def _build_preview_section(self, parent):
        frame = ttk.LabelFrame(parent, text="Preview", padding=8)
        frame.pack(fill=tk.X, pady=(0, 8))
        self.preview_var = tk.StringVar(value="Select an input folder to begin.")
        ttk.Label(frame, textvariable=self.preview_var, justify=tk.LEFT).pack(
            fill=tk.X, anchor=tk.W)

    def _build_action_section(self, parent):
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X)

        self.convert_btn = ttk.Button(
            frame, text="Convert", command=self._start_conversion)
        self.convert_btn.pack(side=tk.RIGHT)

        self.progress = ttk.Progressbar(frame, mode="determinate")
        self.progress.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(0, 8))

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(frame, textvariable=self.status_var, width=40).pack(side=tk.LEFT)

        # Signature / Credits
        sig_frame = ttk.Frame(parent)
        sig_frame.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(sig_frame, text="Tom Wong - Tsinghua University  |  Powered by DeepSeek & Claude Code",
                  foreground="gray").pack(side=tk.RIGHT)

    # ---- Callbacks ---------------------------------------------------------

    def _browse_input(self):
        try:
            d = filedialog.askdirectory(title="Select folder with TIFF files")
            if d:
                self.input_dir_var.set(d)
                self._refresh_file_list()
                self._save_state()
        except Exception:
            logger.exception("Error browsing input folder")
            messagebox.showerror("Error", "Failed to browse input folder.")

    def _refresh_file_list(self, restore=False):
        self.file_listbox.delete(0, tk.END)
        d = self.input_dir_var.get()
        if not d or not os.path.isdir(d):
            self.source_files = []
            self._update_preview()
            return

        try:
            self.source_files = reader.scan_directory(d)
        except Exception as e:
            logger.exception("Error scanning directory")
            messagebox.showerror("Error", f"Failed to scan directory:\n{e}")
            self.source_files = []
            self._update_preview()
            return

        for f in self.source_files:
            self.file_listbox.insert(tk.END, os.path.basename(f))

        if self.source_files and not restore:
            self.file_listbox.select_set(0, tk.END)

        if not restore:
            try:
                meta = reader.parse_scanimage_metadata(self.source_files[0])
                if meta.get("si_slices"):
                    self.z_var.set(meta["si_slices"])
                if meta.get("si_z_step_um"):
                    self.zstep_var.set(meta["si_z_step_um"])
            except Exception:
                logger.warning("Could not auto-detect parameters from metadata")

        self._update_preview()

    def _browse_output(self):
        d = filedialog.askdirectory(title="Select output folder")
        if d:
            self.out_dir_var.set(d)
            self._save_state()

    def _select_all(self):
        self.file_listbox.select_set(0, tk.END)

    def _deselect_all(self):
        self.file_listbox.selection_clear(0, tk.END)

    def _get_selected_files(self):
        indices = self.file_listbox.curselection()
        return [self.source_files[i] for i in indices]

    def _update_preview(self):
        selected = self._get_selected_files()
        if not selected:
            if not self.source_files:
                self.preview_var.set("Select an input folder with TIFF files.")
                return
            self.preview_var.set(
                f"Found {len(self.source_files)} file(s). "
                "Select files to convert (Ctrl+A to select all).")
            return

        try:
            z_per = self.z_var.get()
            t_per = self.t_var.get()
        except tk.TclError:
            self.preview_var.set("Invalid parameter values.")
            return

        try:
            info = reader.read_tiff_info(selected[0])
        except Exception as e:
            self.preview_var.set(f"Failed to read file info:\n{e}")
            return

        n_frames = info["n_frames"]
        y_size, x_size = info["shape"]
        dtype = info["dtype"]
        expected = z_per * t_per

        lines = [
            f"Files selected: {len(selected)}",
            f"Per file: {n_frames} frames ({y_size} x {x_size}, {dtype})",
            f"Layout: {z_per} Z x {t_per} T = {expected} frames/file",
        ]
        if n_frames != expected:
            lines.append(
                f"WARNING: {n_frames} frames/file != {expected} ({z_per}Z x {t_per}T)")
        else:
            total_t = len(selected) * t_per
            lines.append(
                f"Output: {total_t} time points x {z_per} Z slices "
                f"x {y_size} x {x_size}")
            gb = total_t * z_per * y_size * x_size * 2 / (1024**3)
            lines.append(f"Output data size: ~{gb:.2f} GB (uint16)")

        self.preview_var.set("\n".join(lines))

    # ---- Conversion --------------------------------------------------------

    def _start_conversion(self):
        selected = self._get_selected_files()
        if not selected:
            messagebox.showwarning("No files", "Please select TIFF files to convert.")
            return

        out_dir = self.out_dir_var.get()
        if not out_dir:
            messagebox.showwarning("No output", "Please select an output folder.")
            return
        if not os.path.isdir(out_dir):
            try:
                os.makedirs(out_dir)
            except OSError as e:
                logger.exception("Cannot create output folder")
                messagebox.showerror("Error", f"Cannot create output folder:\n{e}")
                return

        try:
            z_per = self.z_var.get()
            t_per = self.t_var.get()
            z_step = self.zstep_var.get()
            xy_str = self.xypix_var.get()
            xy_pixel = float(xy_str) if xy_str != "auto" else 0.9005
        except (tk.TclError, ValueError) as e:
            messagebox.showerror("Invalid parameter", str(e))
            return

        name = self.name_var.get().strip() or "converted"
        fmt = self.format_var.get()

        try:
            first_info = reader.read_tiff_info(selected[0])
            plan = converter.ConversionPlan(
                filepaths=selected,
                z_per_volume=z_per,
                t_per_file=t_per,
                y_size=first_info["shape"][0],
                x_size=first_info["shape"][1],
                dtype=first_info["dtype"],
            )
        except Exception as e:
            logger.exception("Failed to build conversion plan")
            messagebox.showerror("Error", f"Failed to build conversion plan:\n{e}")
            return

        issues = plan.check_consistency()
        if issues:
            msg = "Some files have unexpected frame counts:\n"
            for fp, n in issues[:5]:
                msg += f"  {os.path.basename(fp)}: {n} frames\n"
            if len(issues) > 5:
                msg += f"  ... and {len(issues) - 5} more\n"
            msg += f"\nExpected {z_per * t_per} frames per file."
            msg += "\n\nContinue anyway?"
            if not messagebox.askyesno("Frame count mismatch", msg):
                return

        self._conversion_plan = plan
        self._set_ui_state(tk.DISABLED)
        progress_max = plan.total_t * plan.z_per_volume
        self.progress["maximum"] = progress_max
        self.progress["value"] = 0
        self.status_var.set("Converting...")

        ext = {"ome": ".ome.tif", "ims": ".ims", "series": ".tif"}[fmt]
        out_path = os.path.join(out_dir, f"{name}{ext}")
        logger.info(f"Starting conversion: {fmt} -> {out_path}")

        thread = threading.Thread(
            target=self._run_conversion,
            args=(plan, out_path, name, fmt, z_step, xy_pixel),
            daemon=True)
        thread.start()
        self._poll_thread(thread, progress_max)

    def _run_conversion(self, plan, out_path, name, fmt, z_step, xy_pixel):
        self._convert_error = None
        try:
            if fmt == "ims":
                ims_writer.write_ims(
                    out_path, plan.shape, plan.dtype,
                    plan.iter_timepoints(),
                    z_step_um=z_step, xy_pixel_um=xy_pixel,
                    progress_callback=self._progress_callback)
            elif fmt == "ome":
                tiff2d_writer.write_ome_tiff(
                    out_path, plan.shape, plan.dtype,
                    plan.iter_timepoints(),
                    z_step_um=z_step, xy_pixel_um=xy_pixel,
                    progress_callback=self._progress_callback)
            else:
                tiff2d_writer.write_2d_series(
                    os.path.dirname(out_path), name,
                    plan.shape, plan.dtype,
                    plan.iter_timepoints(),
                    progress_callback=self._progress_callback)
        except Exception as e:
            logger.exception("Conversion failed")
            self._convert_error = str(e)

    def _progress_callback(self, current, total, status_text=None):
        self.root.after(0, self._update_progress, current, total, status_text)

    def _update_progress(self, current, total, status_text=None):
        self.progress["value"] = current
        self.status_var.set(status_text or f"Processing {current}/{total}...")

    def _poll_thread(self, thread, total):
        if thread.is_alive():
            self.root.after(200, self._poll_thread, thread, total)
            return

        self._set_ui_state(tk.NORMAL)
        if self._convert_error:
            logger.error(f"Conversion error: {self._convert_error}")
            messagebox.showerror("Conversion failed", self._convert_error)
            self.status_var.set("Failed")
        else:
            self.progress["value"] = total
            self.status_var.set("Done!")
            fmt = self.format_var.get()
            out_dir = self.out_dir_var.get()
            name = self.name_var.get().strip() or "converted"
            plan = self._conversion_plan

            if fmt == "ims":
                out_path = os.path.join(out_dir, f"{name}.ims")
                msg = f"IMS file saved to:\n{out_path}"
            elif fmt == "ome":
                out_path = os.path.join(out_dir, f"{name}.ome.tif")
                msg = (f"OME-TIFF saved to:\n{out_path}\n\n"
                       f"Open in Imaris: File > Open\n"
                       f"T={plan.total_t}, Z={plan.z_per_volume}")
            else:
                n_files = plan.total_t * plan.z_per_volume
                msg = (f"2D-TIFF series saved to:\n{out_dir}\n\n"
                       f"Files: {name}_T####_Z####.tif\n"
                       f"Total: {n_files} files")

            logger.info(f"Conversion complete: {msg.replace(chr(10), ' ')}")
            messagebox.showinfo("Complete", msg)

    def _set_ui_state(self, state):
        self.convert_btn.config(state=state)


if __name__ == "__main__":
    root = tk.Tk()
    app = Tiff3dConverterApp(root)
    root.mainloop()
