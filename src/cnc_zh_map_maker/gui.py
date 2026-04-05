"""Tkinter GUI for C&C Generals Zero Hour Map Maker.

A simple, user-friendly interface for generating maps from descriptions.
"""

from __future__ import annotations

import os
import json
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from typing import Optional

from cnc_zh_map_maker.map_file import MapFile
from cnc_zh_map_maker.installer import get_zh_maps_folder, install_map


CONFIG_FILE = Path.home() / ".cnc-zh-map-maker.json"

# Color scheme
BG = "#1a1a2e"
BG_LIGHT = "#16213e"
BG_INPUT = "#0f3460"
FG = "#e0e0e0"
FG_DIM = "#888888"
ACCENT = "#e94560"
ACCENT2 = "#0f3460"
SUCCESS = "#00b894"
WARN = "#fdcb6e"


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except Exception:
            pass
    return {}


def save_config(config: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


class MapMakerApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("C&C Generals Zero Hour - Map Maker")
        self.root.geometry("800x700")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)

        self.config = load_config()
        self.current_map: Optional[MapFile] = None
        self.current_map_name: str = ""
        self.temp_dir: Optional[Path] = None
        self.generated_code: str = ""

        self._build_ui()
        self._update_maps_folder()

    def _build_ui(self):
        # Title
        title = tk.Label(
            self.root,
            text="C&C Zero Hour Map Maker",
            font=("Segoe UI", 20, "bold"),
            fg=ACCENT,
            bg=BG,
        )
        title.pack(pady=(15, 5))

        subtitle = tk.Label(
            self.root,
            text="Describe your map and AI will create it",
            font=("Segoe UI", 10),
            fg=FG_DIM,
            bg=BG,
        )
        subtitle.pack(pady=(0, 10))

        # API Key section (collapsible)
        api_frame = tk.LabelFrame(
            self.root,
            text="Settings",
            font=("Segoe UI", 9),
            fg=FG_DIM,
            bg=BG,
            bd=1,
            relief="groove",
        )
        api_frame.pack(fill="x", padx=20, pady=(0, 10))

        api_row = tk.Frame(api_frame, bg=BG)
        api_row.pack(fill="x", padx=10, pady=5)

        tk.Label(api_row, text="API Key:", font=("Segoe UI", 9), fg=FG, bg=BG).pack(side="left")
        self.api_key_var = tk.StringVar(value=self.config.get("api_key", ""))
        self.api_entry = tk.Entry(
            api_row,
            textvariable=self.api_key_var,
            show="*",
            font=("Consolas", 9),
            bg=BG_INPUT,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            width=50,
        )
        self.api_entry.pack(side="left", padx=(10, 5), fill="x", expand=True)

        save_btn = tk.Button(
            api_row,
            text="Save",
            command=self._save_api_key,
            font=("Segoe UI", 8),
            bg=ACCENT2,
            fg=FG,
            relief="flat",
            cursor="hand2",
        )
        save_btn.pack(side="left", padx=5)

        # Maps folder
        folder_row = tk.Frame(api_frame, bg=BG)
        folder_row.pack(fill="x", padx=10, pady=(0, 5))

        tk.Label(folder_row, text="Game folder:", font=("Segoe UI", 9), fg=FG, bg=BG).pack(side="left")
        self.folder_label = tk.Label(
            folder_row,
            text="Detecting...",
            font=("Segoe UI", 9),
            fg=FG_DIM,
            bg=BG,
            anchor="w",
        )
        self.folder_label.pack(side="left", padx=(10, 5), fill="x", expand=True)

        browse_btn = tk.Button(
            folder_row,
            text="Browse",
            command=self._browse_folder,
            font=("Segoe UI", 8),
            bg=ACCENT2,
            fg=FG,
            relief="flat",
            cursor="hand2",
        )
        browse_btn.pack(side="left", padx=5)

        # Description input
        desc_frame = tk.LabelFrame(
            self.root,
            text="Describe your map",
            font=("Segoe UI", 10),
            fg=FG,
            bg=BG,
            bd=1,
            relief="groove",
        )
        desc_frame.pack(fill="x", padx=20, pady=(0, 10))

        self.desc_text = tk.Text(
            desc_frame,
            height=4,
            font=("Segoe UI", 11),
            bg=BG_INPUT,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            wrap="word",
            padx=10,
            pady=8,
        )
        self.desc_text.pack(fill="x", padx=10, pady=10)
        self.desc_text.insert("1.0", "4-player desert map with a central plateau and oil derricks")

        # Examples
        examples_frame = tk.Frame(desc_frame, bg=BG)
        examples_frame.pack(fill="x", padx=10, pady=(0, 8))

        tk.Label(examples_frame, text="Examples:", font=("Segoe UI", 8), fg=FG_DIM, bg=BG).pack(side="left")

        examples = [
            "2p desert with river",
            "4p snow mountains",
            "8p urban sprawl",
            "2p forest chokepoints",
        ]
        for ex in examples:
            btn = tk.Button(
                examples_frame,
                text=ex,
                command=lambda e=ex: self._set_example(e),
                font=("Segoe UI", 8),
                bg=BG_LIGHT,
                fg=FG_DIM,
                relief="flat",
                cursor="hand2",
                padx=6,
                pady=1,
            )
            btn.pack(side="left", padx=3)

        # Generate button
        btn_frame = tk.Frame(self.root, bg=BG)
        btn_frame.pack(fill="x", padx=20, pady=(0, 10))

        self.generate_btn = tk.Button(
            btn_frame,
            text="Generate Map",
            command=self._generate,
            font=("Segoe UI", 13, "bold"),
            bg=ACCENT,
            fg="white",
            relief="flat",
            cursor="hand2",
            padx=30,
            pady=8,
        )
        self.generate_btn.pack(side="left")

        self.status_label = tk.Label(
            btn_frame,
            text="",
            font=("Segoe UI", 10),
            fg=FG_DIM,
            bg=BG,
            anchor="w",
        )
        self.status_label.pack(side="left", padx=15, fill="x", expand=True)

        # Preview area
        preview_frame = tk.LabelFrame(
            self.root,
            text="Preview",
            font=("Segoe UI", 10),
            fg=FG,
            bg=BG,
            bd=1,
            relief="groove",
        )
        preview_frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        preview_inner = tk.Frame(preview_frame, bg=BG)
        preview_inner.pack(fill="both", expand=True, padx=10, pady=10)

        # Left: heightmap image
        self.canvas = tk.Canvas(
            preview_inner,
            width=200,
            height=200,
            bg=BG_LIGHT,
            highlightthickness=0,
        )
        self.canvas.pack(side="left", padx=(0, 15))
        self.canvas.create_text(
            100, 100,
            text="Map preview\nwill appear here",
            fill=FG_DIM,
            font=("Segoe UI", 9),
            justify="center",
        )

        # Right: map info
        self.info_text = tk.Text(
            preview_inner,
            font=("Consolas", 10),
            bg=BG_LIGHT,
            fg=FG,
            relief="flat",
            wrap="word",
            padx=10,
            pady=8,
            state="disabled",
        )
        self.info_text.pack(side="left", fill="both", expand=True)

        # Bottom buttons
        bottom_frame = tk.Frame(self.root, bg=BG)
        bottom_frame.pack(fill="x", padx=20, pady=(0, 15))

        self.install_btn = tk.Button(
            bottom_frame,
            text="Install to Game",
            command=self._install,
            font=("Segoe UI", 12, "bold"),
            bg=SUCCESS,
            fg="white",
            relief="flat",
            cursor="hand2",
            padx=20,
            pady=6,
            state="disabled",
        )
        self.install_btn.pack(side="left")

        self.save_btn = tk.Button(
            bottom_frame,
            text="Save As...",
            command=self._save_as,
            font=("Segoe UI", 10),
            bg=ACCENT2,
            fg=FG,
            relief="flat",
            cursor="hand2",
            padx=15,
            pady=6,
            state="disabled",
        )
        self.save_btn.pack(side="left", padx=10)

        self.install_status = tk.Label(
            bottom_frame,
            text="",
            font=("Segoe UI", 10),
            fg=SUCCESS,
            bg=BG,
            anchor="w",
        )
        self.install_status.pack(side="left", padx=10, fill="x", expand=True)

    def _set_example(self, text: str):
        self.desc_text.delete("1.0", "end")
        self.desc_text.insert("1.0", text)

    def _save_api_key(self):
        self.config["api_key"] = self.api_key_var.get().strip()
        save_config(self.config)
        self._set_status("API key saved", SUCCESS)

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="Select Zero Hour Maps Folder")
        if folder:
            self.config["maps_folder"] = folder
            save_config(self.config)
            self.folder_label.config(text=folder, fg=SUCCESS)

    def _update_maps_folder(self):
        custom = self.config.get("maps_folder")
        if custom and Path(custom).exists():
            self.folder_label.config(text=custom, fg=SUCCESS)
            return

        detected = get_zh_maps_folder()
        if detected:
            self.folder_label.config(text=str(detected), fg=SUCCESS)
        else:
            self.folder_label.config(text="Not found (use Browse to set)", fg=WARN)

    def _set_status(self, text: str, color: str = FG_DIM):
        self.status_label.config(text=text, fg=color)
        self.root.update_idletasks()

    def _generate(self):
        description = self.desc_text.get("1.0", "end").strip()
        if not description:
            messagebox.showwarning("Empty", "Please describe the map you want to create.")
            return

        api_key = self.api_key_var.get().strip()

        self.generate_btn.config(state="disabled", text="Generating...")
        self._set_status("Creating map...", WARN)

        # Run in background thread
        thread = threading.Thread(
            target=self._generate_worker,
            args=(description, api_key),
            daemon=True,
        )
        thread.start()

    def _generate_worker(self, description: str, api_key: str):
        try:
            if api_key:
                from cnc_zh_map_maker.ai_generator import generate_map_from_description
                map_file, map_name, code = generate_map_from_description(description, api_key)
                self.generated_code = code
            else:
                from cnc_zh_map_maker.ai_generator import generate_map_offline
                map_file, map_name = generate_map_offline(description)
                self.generated_code = "(offline mode)"

            self.current_map = map_file
            self.current_map_name = map_name

            # Save to temp dir
            self.temp_dir = Path(tempfile.mkdtemp(prefix="zhmap_"))
            map_dir = self.temp_dir / map_name
            map_dir.mkdir(parents=True, exist_ok=True)
            map_file.save(map_dir / f"{map_name}.map")

            # Generate preview TGA
            from cnc_zh_map_maker.builder import MapBuilder
            builder = MapBuilder.__new__(MapBuilder)
            builder._width = map_file.height_map.width
            builder._height = map_file.height_map.height
            builder._base_elevation = 400
            builder._generate_preview_tga(map_dir / f"{map_name}.tga")

            self.root.after(0, self._on_generate_success)

        except Exception as e:
            error_msg = str(e)
            self.root.after(0, lambda: self._on_generate_error(error_msg))

    def _on_generate_success(self):
        self.generate_btn.config(state="normal", text="Generate Map")
        self._set_status(f"Map '{self.current_map_name}' created!", SUCCESS)
        self.install_btn.config(state="normal")
        self.save_btn.config(state="normal")

        # Update preview
        self._update_preview()

    def _on_generate_error(self, error: str):
        self.generate_btn.config(state="normal", text="Generate Map")
        self._set_status(f"Error: {error}", ACCENT)
        messagebox.showerror("Generation Error", error)

    def _update_preview(self):
        if self.current_map is None:
            return

        mf = self.current_map
        hm = mf.height_map

        # Draw heightmap on canvas
        self.canvas.delete("all")
        canvas_w = 200
        canvas_h = 200

        if hm.elevations:
            # Find min/max elevation
            flat = [v for row in hm.elevations for v in row]
            min_e = min(flat)
            max_e = max(flat)
            e_range = max(1, max_e - min_e)

            # Draw pixels (scaled to canvas)
            # Use PhotoImage for pixel-level drawing
            img = tk.PhotoImage(width=canvas_w, height=canvas_h)
            self.canvas.create_image(0, 0, anchor="nw", image=img)
            self._preview_image = img  # Keep reference

            for cy in range(canvas_h):
                row_data = []
                for cx in range(canvas_w):
                    hx = int(cx * hm.width / canvas_w)
                    hy = int(cy * hm.height / canvas_h)
                    hx = min(hx, hm.width - 1)
                    hy = min(hy, hm.height - 1)

                    val = hm.elevations[hy][hx]
                    norm = (val - min_e) / e_range
                    # Terrain-like coloring
                    r = int(80 + norm * 100)
                    g = int(100 + norm * 120)
                    b = int(60 + norm * 60)
                    row_data.append(f"#{r:02x}{g:02x}{b:02x}")

                img.put("{" + " ".join(row_data) + "}", to=(0, cy))

            # Draw player starts
            for wp in mf.waypoints.waypoints:
                if "Start" in wp.name:
                    px = int(wp.position.x * canvas_w / hm.width)
                    py = int(wp.position.y * canvas_h / hm.height)
                    self.canvas.create_oval(
                        px - 5, py - 5, px + 5, py + 5,
                        fill=ACCENT, outline="white", width=1,
                    )
                    self.canvas.create_text(
                        px, py - 10,
                        text=wp.name.replace("Player_", "P").replace("_Start", ""),
                        fill="white",
                        font=("Segoe UI", 7, "bold"),
                    )

        # Update info text
        self.info_text.config(state="normal")
        self.info_text.delete("1.0", "end")

        info = [
            f"Name: {mf.world_info.map_name}",
            f"Size: {hm.width} x {hm.height}",
            f"Weather: {mf.world_info.weather.name}",
            f"",
            f"Textures: {len(mf.blend_tile_data.textures)}",
        ]
        for t in mf.blend_tile_data.textures:
            info.append(f"  - {t.name}")

        info.extend([
            f"",
            f"Objects: {len(mf.objects)}",
        ])

        # Count object types
        type_counts: dict[str, int] = {}
        for obj in mf.objects:
            cat = _categorize_object(obj.type_name)
            type_counts[cat] = type_counts.get(cat, 0) + 1
        for cat, count in sorted(type_counts.items()):
            info.append(f"  {cat}: {count}")

        info.extend([
            f"",
            f"Players: {len(mf.sides.players)}",
        ])
        for p in mf.sides.players:
            if p.name:
                info.append(f"  {p.display_name or p.name}")

        starts = [w for w in mf.waypoints.waypoints if "Start" in w.name]
        if starts:
            info.append(f"")
            info.append(f"Spawn points: {len(starts)}")

        info.extend([
            f"",
            f"Waypoints: {len(mf.waypoints.waypoints)}",
            f"AI Triggers: {len(mf.polygon_triggers)}",
        ])

        self.info_text.insert("1.0", "\n".join(info))
        self.info_text.config(state="disabled")

    def _install(self):
        if self.current_map is None or self.temp_dir is None:
            return

        maps_folder = None
        custom = self.config.get("maps_folder")
        if custom:
            maps_folder = Path(custom)
        else:
            maps_folder = get_zh_maps_folder()

        if maps_folder is None:
            result = messagebox.askyesno(
                "Maps Folder Not Found",
                "Could not auto-detect the game's maps folder.\n\n"
                "Would you like to browse for it?",
            )
            if result:
                self._browse_folder()
                maps_folder_str = self.config.get("maps_folder")
                if maps_folder_str:
                    maps_folder = Path(maps_folder_str)

        if maps_folder is None:
            return

        try:
            map_path = self.temp_dir / self.current_map_name / f"{self.current_map_name}.map"
            dest = install_map(map_path, maps_folder)
            self.install_status.config(
                text=f"Installed to {dest.name}/",
                fg=SUCCESS,
            )
            messagebox.showinfo(
                "Installed!",
                f"Map '{self.current_map_name}' has been installed.\n\n"
                f"Location: {dest}\n\n"
                "Launch the game and look for it in Skirmish map selection!",
            )
        except Exception as e:
            messagebox.showerror("Install Error", str(e))

    def _save_as(self):
        if self.current_map is None:
            return

        folder = filedialog.askdirectory(title="Save Map To...")
        if not folder:
            return

        dest = Path(folder) / self.current_map_name
        dest.mkdir(parents=True, exist_ok=True)
        self.current_map.save(dest / f"{self.current_map_name}.map")

        # Also save TGA
        from cnc_zh_map_maker.builder import MapBuilder
        builder = MapBuilder.__new__(MapBuilder)
        builder._width = self.current_map.height_map.width
        builder._height = self.current_map.height_map.height
        builder._base_elevation = 400
        builder._generate_preview_tga(dest / f"{self.current_map_name}.tga")

        self.install_status.config(text=f"Saved to {dest}", fg=SUCCESS)

    def run(self):
        self.root.mainloop()


def _categorize_object(type_name: str) -> str:
    t = type_name.lower()
    if "tree" in t or "bush" in t:
        return "Trees/Vegetation"
    elif "rock" in t or "boulder" in t:
        return "Rocks"
    elif "civ" in t or "house" in t:
        return "Civilian Buildings"
    elif "tech" in t or "oil" in t or "hospital" in t:
        return "Tech Buildings"
    elif "supply" in t:
        return "Supply Docks"
    elif "barrel" in t or "crate" in t or "fence" in t or "lamp" in t:
        return "Props"
    else:
        return "Other"


def main():
    app = MapMakerApp()
    app.run()


if __name__ == "__main__":
    main()
