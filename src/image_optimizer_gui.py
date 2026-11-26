# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10"]
# ///
"""Interface graphique de image_optimizer (compilée en ../ImageOptimizer.exe par build_exe.py)."""
from __future__ import annotations

import json
import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import image_optimizer as core

BG, FG, ACCENT, MUTED = "#F2F2F2", "#1C1C1E", "#007AFF", "#8E8E93"
# Réglages propres au PC (dossier des originaux), gardés hors du dépôt.
SETTINGS = Path(os.environ.get("APPDATA") or Path.home()) / "ImageOptimizer" / "settings.json"


def load_settings() -> dict:
    try:
        data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(data: dict) -> None:
    try:
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass  # un réglage non gardé ne bloque pas le traitement


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("Image Optimizer")
        root.configure(bg=BG)
        root.geometry("680x620")
        root.minsize(620, 560)
        self.files: list[Path] = []

        pad = {"padx": 14, "pady": 6}
        self._label("Image(s), GIF ou dossier").pack(anchor="w", **pad)
        row = tk.Frame(root, bg=BG)
        row.pack(fill="x", padx=14)
        self.src = tk.Entry(row, font=("Segoe UI", 10), relief="groove", bd=2)
        self.src.pack(side="left", fill="x", expand=True)
        self._button(row, "Fichiers…", self.pick_files).pack(side="left", padx=4)
        self._button(row, "Dossier…", self.pick_folder).pack(side="left")
        self.info = tk.Label(root, text="", bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.info.pack(anchor="w", padx=14)

        grid = tk.Frame(root, bg=BG)
        grid.pack(fill="x", padx=14, pady=8)
        self._label("Taille", grid).grid(row=0, column=0, sticky="w")
        self.preset = ttk.Combobox(grid, state="readonly", width=22,
                                   values=list(core.PRESET_LABELS.values()) + ["Personnalisée"])
        self.preset.set(core.PRESET_LABELS["hd"])
        self.preset.grid(row=0, column=1, sticky="w", padx=8)
        self.preset.bind("<<ComboboxSelected>>", lambda e: self._toggle_custom())
        self._label("Largeur (px)", grid).grid(row=0, column=2, sticky="w", padx=(16, 0))
        self.custom = tk.Entry(grid, width=8, font=("Segoe UI", 10), relief="groove", bd=2)
        self.custom.insert(0, "1000")
        self.custom.grid(row=0, column=3, sticky="w", padx=8)
        self._toggle_custom()

        self._label("Format", grid).grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.fmt = ttk.Combobox(grid, state="readonly", width=22,
                                values=["WebP (recommandé)", "Garder le format"])
        self.fmt.set("WebP (recommandé)")
        self.fmt.grid(row=1, column=1, sticky="w", padx=8, pady=(8, 0))
        tk.Label(grid, text="Jamais agrandie · transparence gardée · GIF : 15 i/s max",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9)).grid(row=1, column=2, columnspan=2, sticky="w", padx=(16, 0), pady=(8, 0))

        self._label("Dossier de sortie (vide = sous-dossier « optimized » à côté des images)").pack(anchor="w", **pad)
        self.out = self._path_row(self.pick_out)

        self.keep_orig = tk.BooleanVar(value=False)
        tk.Checkbutton(root, text="Garder un original HD (webp, max 1920 px) pour refaire plus grand plus tard",
                       variable=self.keep_orig, bg=BG, fg=FG, activebackground=BG, font=("Segoe UI", 10),
                       command=self._toggle_orig).pack(anchor="w", padx=10, pady=(8, 0))
        self.orig = self._path_row(self.pick_orig)
        saved = load_settings().get("originals")
        self.orig.insert(0, saved if isinstance(saved, str) else "")
        self._toggle_orig()

        self.run_btn = self._button(root, "Optimiser", self.run, big=True)
        self.run_btn.pack(pady=12)
        self.bar = ttk.Progressbar(root, mode="determinate")
        self.bar.pack(fill="x", padx=14)
        self.log = tk.Text(root, height=10, font=("Consolas", 9), relief="flat", bg="white")
        self.log.pack(fill="both", expand=True, padx=14, pady=10)

    # --- widgets -----------------------------------------------------------
    def _label(self, text: str, parent: tk.Misc | None = None) -> tk.Label:
        return tk.Label(parent or self.root, text=text, bg=BG, fg=FG, font=("Segoe UI", 10, "bold"))

    def _button(self, parent: tk.Misc, text: str, cmd, big: bool = False) -> tk.Button:
        return tk.Button(parent, text=text, command=cmd, bg=ACCENT, fg="white", bd=0, relief="flat",
                         activebackground="#0062CC", activeforeground="white",
                         font=("Segoe UI", 11 if big else 9, "bold"), padx=18 if big else 10, pady=4)

    def _path_row(self, cmd) -> tk.Entry:
        row = tk.Frame(self.root, bg=BG)
        row.pack(fill="x", padx=14)
        entry = tk.Entry(row, font=("Segoe UI", 10), relief="groove", bd=2)
        entry.pack(side="left", fill="x", expand=True)
        self._button(row, "Choisir…", cmd).pack(side="left", padx=4)
        return entry

    def _toggle_custom(self) -> None:
        self.custom.config(state="normal" if self.preset.get() == "Personnalisée" else "disabled")

    def _toggle_orig(self) -> None:
        self.orig.config(state="normal" if self.keep_orig.get() else "disabled")

    # --- choix -------------------------------------------------------------
    def _set_sources(self, paths: list[str]) -> None:
        self.files = core.collect(paths)
        self.src.delete(0, tk.END)
        self.src.insert(0, " ; ".join(paths))
        kb = sum(f.stat().st_size for f in self.files) / 1024
        self.info.config(text=f"{len(self.files)} image(s), {kb:,.0f} Ko au total".replace(",", " "))

    def pick_files(self) -> None:
        paths = filedialog.askopenfilenames(title="Images", filetypes=[("Images", "*.jpg *.jpeg *.png *.webp *.gif *.bmp *.tif *.tiff")])
        if paths:
            self._set_sources(list(paths))

    def pick_folder(self) -> None:
        folder = filedialog.askdirectory(title="Dossier d'images")
        if folder:
            self._set_sources([folder])

    def pick_out(self) -> None:
        folder = filedialog.askdirectory(title="Dossier de sortie")
        if folder:
            self.out.delete(0, tk.END)
            self.out.insert(0, folder)

    def pick_orig(self) -> None:
        folder = filedialog.askdirectory(title="Dossier des originaux")
        if folder:
            self.orig.delete(0, tk.END)
            self.orig.insert(0, folder)

    # --- traitement ----------------------------------------------------------
    def _max_width(self) -> int:
        label = self.preset.get()
        if label == "Personnalisée":
            return int(self.custom.get())
        return next(core.PRESETS[k] for k, v in core.PRESET_LABELS.items() if v == label)

    def run(self) -> None:
        if not self.files and self.src.get().strip():
            self._set_sources([s.strip() for s in self.src.get().split(";") if s.strip()])
        if not self.files:
            messagebox.showerror("Image Optimizer", "Choisis au moins une image ou un dossier.")
            return
        try:
            max_w = self._max_width()
        except ValueError:
            messagebox.showerror("Image Optimizer", "Largeur personnalisée invalide.")
            return
        out = Path(self.out.get().strip()) if self.out.get().strip() else self.files[0].parent / "optimized"
        orig = Path(self.orig.get().strip()).expanduser().resolve() if self.keep_orig.get() and self.orig.get().strip() else None
        mode = "webp" if self.fmt.get().startswith("WebP") else "keep"
        if orig:
            save_settings({**load_settings(), "originals": str(orig)})
        self.run_btn.config(state="disabled")
        self.bar.config(value=0, maximum=len(self.files))
        self.log.delete("1.0", tk.END)
        threading.Thread(target=self._work, args=(out, max_w, mode, orig), daemon=True).start()

    def _work(self, out: Path, max_w: int, mode: str, orig: Path | None) -> None:
        totals = [0.0, 0.0]

        def progress(i: int, n: int, r, f: Path) -> None:
            if isinstance(r, Exception):
                line = f"ERREUR {f.name} : {r}\n"
            else:
                totals[0] += r["before"]["size_kb"]
                totals[1] += r["size_kb"]
                extra = f", {r['frames_before']}→{r['frames_after']} images" if "frames_before" in r else ""
                line = (f"{f.name} : {r['before']['width']}→{r['width']} px, "
                        f"{r['before']['size_kb']}→{r['size_kb']} Ko{extra}\n")
            self.root.after(0, self._progress, i, line)

        core.run_batch(self.files, out, max_w, mode, orig, progress)
        self.root.after(0, self._done, out, totals)

    def _progress(self, i: int, line: str) -> None:
        self.bar.config(value=i)
        self.log.insert(tk.END, line)
        self.log.see(tk.END)

    def _done(self, out: Path, totals: list[float]) -> None:
        self.run_btn.config(state="normal")
        gain = (1 - totals[1] / totals[0]) * 100 if totals[0] else 0
        self.log.insert(tk.END, f"\nTerminé : {totals[0]:.0f} → {totals[1]:.0f} Ko (-{gain:.0f} %). Sortie : {out}\n")
        self.log.see(tk.END)


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
