"""Tkinter GUI for C&C Generals Zero Hour Map Maker.

Modern dark-themed interface for generating maps from text descriptions.
Layout: header / scrollable body / sticky action footer — so the primary
actions (Generate / Install / Save) are always reachable regardless of
window size.
"""

from __future__ import annotations

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

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------
COLORS = {
    "bg":        "#0f1419",
    "surface":   "#1a1f29",
    "surface_2": "#252b38",
    "input":     "#161a23",
    "border":    "#2a3142",
    "text":      "#e6e9ee",
    "text_dim":  "#8b94a3",
    "text_mute": "#5b6478",
    "primary":   "#ff4d6d",
    "primary_h": "#ff6b85",
    "success":   "#10b981",
    "success_h": "#34d399",
    "warn":      "#f59e0b",
    "info":      "#60a5fa",
}

FONT_DISPLAY = ("Segoe UI", 22, "bold")
FONT_HEADING = ("Segoe UI", 11, "bold")
FONT_BODY    = ("Segoe UI", 10)
FONT_SMALL   = ("Segoe UI", 9)
FONT_MONO    = ("Consolas", 10)


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except Exception:
            pass
    return {}


def save_config(config: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


class HoverButton(tk.Button):
    """tk.Button with a reliable hover background.

    ttk.Button doesn't honor custom backgrounds on Windows with most themes,
    so the whole UI uses tk.Button styled by hand for consistency.
    """

    def __init__(self, master, *, hover_bg=None, hover_fg=None, **kwargs):
        super().__init__(master, **kwargs)
        self._normal_bg = kwargs.get("bg")
        self._normal_fg = kwargs.get("fg")
        self._hover_bg = hover_bg or self._normal_bg
        self._hover_fg = hover_fg or self._normal_fg
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _):
        if str(self["state"]) != "disabled":
            self.config(bg=self._hover_bg, fg=self._hover_fg)

    def _on_leave(self, _):
        if str(self["state"]) != "disabled":
            self.config(bg=self._normal_bg, fg=self._normal_fg)

    def set_palette(self, *, bg=None, hover_bg=None, fg=None, hover_fg=None):
        if bg is not None:
            self._normal_bg = bg
            self.config(bg=bg)
        if hover_bg is not None:
            self._hover_bg = hover_bg
        if fg is not None:
            self._normal_fg = fg
            self.config(fg=fg)
        if hover_fg is not None:
            self._hover_fg = hover_fg


class MapMakerApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("C&C Zero Hour — Map Maker")
        self.root.configure(bg=COLORS["bg"])
        self._set_geometry(960, 820, min_width=720, min_height=600)

        self.config = load_config()
        self.current_map: Optional[MapFile] = None
        self.current_map_name: str = ""
        self.temp_dir: Optional[Path] = None
        self.generated_code: str = ""
        self._preview_image = None

        self._setup_styles()
        self._build_ui()
        self._update_maps_folder()
        self._refresh_api_status()

        self.root.bind("<Control-Return>", lambda _: self._generate())

    def _set_geometry(self, w, h, *, min_width, min_height):
        self.root.minsize(min_width, min_height)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2 - 30)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _setup_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        c = COLORS
        style.configure("Modern.Vertical.TScrollbar",
                        background=c["surface_2"], troughcolor=c["bg"],
                        bordercolor=c["bg"], arrowcolor=c["text_dim"],
                        lightcolor=c["surface_2"], darkcolor=c["surface_2"])
        style.map("Modern.Vertical.TScrollbar",
                  background=[("active", c["border"])])

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_ui(self):
        c = COLORS

        self.root.rowconfigure(1, weight=1)
        self.root.columnconfigure(0, weight=1)

        self._build_header()
        self._build_body()
        self._build_footer()

    def _build_header(self):
        c = COLORS
        header = tk.Frame(self.root, bg=c["bg"], padx=24, pady=18)
        header.grid(row=0, column=0, sticky="ew")

        title_row = tk.Frame(header, bg=c["bg"])
        title_row.pack(fill="x")

        tk.Label(title_row, text="ZH Map Maker", font=FONT_DISPLAY,
                 fg=c["primary"], bg=c["bg"]).pack(side="left")
        tk.Label(title_row,
                 text="AI-generated maps for C&C Generals: Zero Hour",
                 font=FONT_SMALL, fg=c["text_dim"], bg=c["bg"]).pack(
            side="left", padx=(14, 0), pady=(12, 0))

    def _build_body(self):
        c = COLORS
        body_outer = tk.Frame(self.root, bg=c["bg"])
        body_outer.grid(row=1, column=0, sticky="nsew", padx=24)
        body_outer.rowconfigure(0, weight=1)
        body_outer.columnconfigure(0, weight=1)

        canvas = tk.Canvas(body_outer, bg=c["bg"], bd=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(body_outer, orient="vertical",
                                  style="Modern.Vertical.TScrollbar",
                                  command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        body = tk.Frame(canvas, bg=c["bg"])
        body_window = canvas.create_window((0, 0), window=body, anchor="nw")

        def _on_body_configure(_=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfig(body_window, width=event.width)

        body.bind("<Configure>", _on_body_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        # Mouse-wheel scroll only when pointer is inside the body
        def _on_enter(_):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
            canvas.bind_all("<Button-4>",   lambda e: canvas.yview_scroll(-1, "units"))
            canvas.bind_all("<Button-5>",   lambda e: canvas.yview_scroll( 1, "units"))

        def _on_leave(_):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<Enter>", _on_enter)
        canvas.bind("<Leave>", _on_leave)

        self._build_settings_card(body)
        self._build_description_card(body)
        self._build_preview_card(body)

    def _build_footer(self):
        c = COLORS

        # 1px divider
        divider = tk.Frame(self.root, bg=c["border"], height=1)
        divider.grid(row=2, column=0, sticky="ew")

        footer = tk.Frame(self.root, bg=c["surface"], padx=24, pady=14)
        footer.grid(row=3, column=0, sticky="ew")

        self.generate_btn = HoverButton(
            footer, text="Generate Map", command=self._generate,
            font=("Segoe UI", 12, "bold"),
            bg=c["primary"], hover_bg=c["primary_h"],
            fg="white", hover_fg="white",
            relief="flat", bd=0, cursor="hand2",
            padx=24, pady=10,
        )
        self.generate_btn.pack(side="left")

        self.install_btn = HoverButton(
            footer, text="Install to Game", command=self._install,
            font=("Segoe UI", 11, "bold"),
            bg=c["surface_2"], hover_bg=c["surface_2"],
            fg=c["text_mute"], hover_fg=c["text_mute"],
            relief="flat", bd=0, cursor="arrow",
            padx=18, pady=10, state="disabled",
        )
        self.install_btn.pack(side="left", padx=(12, 0))

        self.save_btn = HoverButton(
            footer, text="Save As…", command=self._save_as,
            font=("Segoe UI", 11),
            bg=c["surface_2"], hover_bg=c["surface_2"],
            fg=c["text_mute"], hover_fg=c["text_mute"],
            relief="flat", bd=0, cursor="arrow",
            padx=14, pady=10, state="disabled",
        )
        self.save_btn.pack(side="left", padx=(8, 0))

        self.status_label = tk.Label(
            footer, text="Ready", font=FONT_SMALL,
            fg=c["text_dim"], bg=c["surface"], anchor="e",
        )
        self.status_label.pack(side="right")

    # ------------------------------------------------------------------
    # Cards
    # ------------------------------------------------------------------
    def _build_settings_card(self, parent):
        c = COLORS
        card = tk.Frame(parent, bg=c["surface"], padx=18, pady=16,
                        highlightthickness=1, highlightbackground=c["border"])
        card.pack(fill="x", pady=(8, 12))

        head = tk.Frame(card, bg=c["surface"])
        head.pack(fill="x", pady=(0, 12))
        tk.Label(head, text="Settings", font=FONT_HEADING,
                 fg=c["text"], bg=c["surface"]).pack(side="left")
        self.api_status = tk.Label(head, text="• no API key",
                                   font=FONT_SMALL, fg=c["warn"], bg=c["surface"])
        self.api_status.pack(side="right")

        tk.Label(card, text="Anthropic API Key", font=FONT_SMALL,
                 fg=c["text_dim"], bg=c["surface"]).pack(anchor="w")
        api_row = tk.Frame(card, bg=c["surface"])
        api_row.pack(fill="x", pady=(4, 6))

        self.api_key_var = tk.StringVar(value=self.config.get("api_key", ""))
        self.api_key_var.trace_add("write", lambda *_: self._refresh_api_status())
        self.api_entry = tk.Entry(
            api_row, textvariable=self.api_key_var, show="•",
            font=FONT_MONO, bg=c["input"], fg=c["text"],
            insertbackground=c["text"], relief="flat", bd=0,
            highlightthickness=1, highlightbackground=c["border"],
            highlightcolor=c["primary"],
        )
        self.api_entry.pack(side="left", fill="x", expand=True,
                            ipady=8, padx=(0, 8))

        HoverButton(api_row, text="Save", command=self._save_api_key,
                    font=FONT_BODY, bg=c["surface_2"], hover_bg=c["info"],
                    fg=c["text"], hover_fg="white",
                    relief="flat", bd=0, cursor="hand2",
                    padx=18, pady=7).pack(side="left")

        tk.Label(card,
                 text="Without a key the app falls back to a basic offline template (low variety).",
                 font=FONT_SMALL, fg=c["text_mute"], bg=c["surface"],
                 wraplength=820, justify="left").pack(anchor="w", pady=(0, 14))

        tk.Label(card, text="Zero Hour Maps Folder", font=FONT_SMALL,
                 fg=c["text_dim"], bg=c["surface"]).pack(anchor="w")
        folder_row = tk.Frame(card, bg=c["surface"])
        folder_row.pack(fill="x", pady=(4, 0))

        self.folder_label = tk.Label(folder_row, text="Detecting…", anchor="w",
                                     font=("Consolas", 9), fg=c["text_dim"],
                                     bg=c["input"], padx=12, pady=8)
        self.folder_label.pack(side="left", fill="x", expand=True,
                               padx=(0, 8), ipady=0)

        HoverButton(folder_row, text="Browse", command=self._browse_folder,
                    font=FONT_BODY, bg=c["surface_2"], hover_bg=c["info"],
                    fg=c["text"], hover_fg="white",
                    relief="flat", bd=0, cursor="hand2",
                    padx=18, pady=7).pack(side="left")

    def _build_description_card(self, parent):
        c = COLORS
        card = tk.Frame(parent, bg=c["surface"], padx=18, pady=16,
                        highlightthickness=1, highlightbackground=c["border"])
        card.pack(fill="x", pady=(0, 12))

        head = tk.Frame(card, bg=c["surface"])
        head.pack(fill="x", pady=(0, 8))
        tk.Label(head, text="Describe your map", font=FONT_HEADING,
                 fg=c["text"], bg=c["surface"]).pack(side="left")
        tk.Label(head, text="Ctrl+Enter to generate", font=FONT_SMALL,
                 fg=c["text_mute"], bg=c["surface"]).pack(side="right")

        self.desc_text = tk.Text(card, height=4, font=("Segoe UI", 11),
                                 bg=c["input"], fg=c["text"],
                                 insertbackground=c["text"],
                                 relief="flat", bd=0, wrap="word",
                                 padx=12, pady=10,
                                 highlightthickness=1,
                                 highlightbackground=c["border"],
                                 highlightcolor=c["primary"])
        self.desc_text.pack(fill="x")
        self.desc_text.insert("1.0",
                              "4-player desert map with a central plateau and oil derricks")

        ex_row = tk.Frame(card, bg=c["surface"])
        ex_row.pack(fill="x", pady=(10, 0))
        tk.Label(ex_row, text="Try:", font=FONT_SMALL,
                 fg=c["text_mute"], bg=c["surface"]).pack(side="left",
                                                          padx=(0, 8))
        for ex in [
            "2p desert + river",
            "4p snow mountains",
            "8p urban sprawl",
            "2p forest chokepoints",
        ]:
            HoverButton(ex_row, text=ex,
                        command=lambda e=ex: self._set_example(e),
                        font=FONT_SMALL, bg=c["surface_2"], hover_bg=c["info"],
                        fg=c["text_dim"], hover_fg="white",
                        relief="flat", bd=0, cursor="hand2",
                        padx=10, pady=4).pack(side="left", padx=3)

    def _build_preview_card(self, parent):
        c = COLORS
        card = tk.Frame(parent, bg=c["surface"], padx=18, pady=16,
                        highlightthickness=1, highlightbackground=c["border"])
        card.pack(fill="both", expand=True, pady=(0, 18))

        tk.Label(card, text="Preview", font=FONT_HEADING,
                 fg=c["text"], bg=c["surface"]).pack(anchor="w", pady=(0, 12))

        inner = tk.Frame(card, bg=c["surface"])
        inner.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(inner, width=260, height=260,
                                bg=c["input"], highlightthickness=1,
                                highlightbackground=c["border"], bd=0)
        self.canvas.pack(side="left", padx=(0, 16))
        self.canvas.create_text(130, 130,
            text="Map preview\nappears here\nafter generating",
            fill=c["text_mute"], font=FONT_SMALL, justify="center")

        info_wrap = tk.Frame(inner, bg=c["input"], padx=14, pady=12,
                             highlightthickness=1,
                             highlightbackground=c["border"])
        info_wrap.pack(side="left", fill="both", expand=True)

        self.info_text = tk.Text(info_wrap, font=FONT_MONO,
                                 bg=c["input"], fg=c["text"], relief="flat",
                                 wrap="word", bd=0, state="disabled",
                                 height=14)
        self.info_text.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    # Behavior
    # ------------------------------------------------------------------
    def _set_example(self, text: str):
        self.desc_text.delete("1.0", "end")
        self.desc_text.insert("1.0", text)

    def _save_api_key(self):
        self.config["api_key"] = self.api_key_var.get().strip()
        save_config(self.config)
        self._set_status("API key saved", COLORS["success"])
        self._refresh_api_status()

    def _refresh_api_status(self):
        if (self.api_key_var.get() or "").strip():
            self.api_status.config(text="● AI mode", fg=COLORS["success"])
        else:
            self.api_status.config(text="● offline (basic) mode", fg=COLORS["warn"])

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="Select Zero Hour Maps Folder")
        if folder:
            self.config["maps_folder"] = folder
            save_config(self.config)
            self.folder_label.config(text=folder, fg=COLORS["success"])

    def _update_maps_folder(self):
        custom = self.config.get("maps_folder")
        if custom and Path(custom).exists():
            self.folder_label.config(text=custom, fg=COLORS["success"])
            return
        detected = get_zh_maps_folder()
        if detected:
            self.folder_label.config(text=str(detected), fg=COLORS["success"])
        else:
            self.folder_label.config(
                text="Not found — click Browse to set",
                fg=COLORS["warn"])

    def _set_status(self, text: str, color: str = None):
        self.status_label.config(text=text, fg=color or COLORS["text_dim"])
        self.root.update_idletasks()

    def _generate(self):
        if str(self.generate_btn["state"]) == "disabled":
            return
        description = self.desc_text.get("1.0", "end").strip()
        if not description:
            messagebox.showwarning("Empty", "Please describe the map you want to create.")
            return

        api_key = self.api_key_var.get().strip()
        self.generate_btn.config(state="disabled", text="Generating…")
        self._set_status("Creating map…", COLORS["warn"])

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

            self.temp_dir = Path(tempfile.mkdtemp(prefix="zhmap_"))
            map_dir = self.temp_dir / map_name
            map_dir.mkdir(parents=True, exist_ok=True)
            map_file.save(map_dir / f"{map_name}.map")

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
        c = COLORS
        self.generate_btn.config(state="normal", text="Generate Map")
        self._set_status(f"Created '{self.current_map_name}'", c["success"])

        self.install_btn.config(state="normal", cursor="hand2")
        self.install_btn.set_palette(bg=c["success"], hover_bg=c["success_h"],
                                     fg="white", hover_fg="white")
        self.save_btn.config(state="normal", cursor="hand2")
        self.save_btn.set_palette(bg=c["surface_2"], hover_bg=c["info"],
                                  fg=c["text"], hover_fg="white")

        self._update_preview()

    def _on_generate_error(self, error: str):
        self.generate_btn.config(state="normal", text="Generate Map")
        self._set_status(f"Error: {error}", COLORS["primary"])
        messagebox.showerror("Generation Error", error)

    def _update_preview(self):
        if self.current_map is None:
            return
        c = COLORS
        mf = self.current_map
        hm = mf.height_map

        self.canvas.delete("all")
        cw = ch = 260

        if hm.elevations:
            flat = [v for row in hm.elevations for v in row]
            min_e, max_e = min(flat), max(flat)
            e_range = max(1, max_e - min_e)

            img = tk.PhotoImage(width=cw, height=ch)
            self.canvas.create_image(0, 0, anchor="nw", image=img)
            self._preview_image = img

            for cy in range(ch):
                row = []
                for cx in range(cw):
                    hx = min(int(cx * hm.width / cw), hm.width - 1)
                    hy = min(int(cy * hm.height / ch), hm.height - 1)
                    val = hm.elevations[hy][hx]
                    norm = (val - min_e) / e_range
                    r = int(80 + norm * 100)
                    g = int(100 + norm * 120)
                    b = int(60 + norm * 60)
                    row.append(f"#{r:02x}{g:02x}{b:02x}")
                img.put("{" + " ".join(row) + "}", to=(0, cy))

            for wp in mf.waypoints.waypoints:
                if "Start" in wp.name:
                    px = int(wp.position.x * cw / hm.width)
                    py = int(wp.position.y * ch / hm.height)
                    self.canvas.create_oval(px - 7, py - 7, px + 7, py + 7,
                                            fill=c["primary"], outline="white",
                                            width=2)
                    self.canvas.create_text(
                        px, py - 14,
                        text=wp.name.replace("Player_", "P").replace("_Start", ""),
                        fill="white", font=("Segoe UI", 8, "bold"))

        # Info text
        self.info_text.config(state="normal")
        self.info_text.delete("1.0", "end")

        info = [
            f"  {mf.world_info.map_name}",
            f"  {hm.width} × {hm.height}  ({mf.world_info.weather.name.lower()})",
            "",
            f"  Textures ({len(mf.blend_tile_data.textures)})",
        ]
        for t in mf.blend_tile_data.textures[:5]:
            info.append(f"    • {t.name}")
        if len(mf.blend_tile_data.textures) > 5:
            info.append(f"    + {len(mf.blend_tile_data.textures) - 5} more")

        info += ["", f"  Objects ({len(mf.objects)})"]
        type_counts: dict[str, int] = {}
        for obj in mf.objects:
            cat = _categorize_object(obj.type_name)
            type_counts[cat] = type_counts.get(cat, 0) + 1
        for cat, count in sorted(type_counts.items()):
            info.append(f"    • {cat}: {count}")

        info += ["", f"  Players ({len(mf.sides.players)})"]
        for p in mf.sides.players:
            if p.name:
                info.append(f"    • {p.display_name or p.name}")

        starts = [w for w in mf.waypoints.waypoints if "Start" in w.name]
        if starts:
            info += ["", f"  Spawn points: {len(starts)}"]

        info += [
            "",
            f"  Waypoints: {len(mf.waypoints.waypoints)}",
            f"  AI triggers: {len(mf.polygon_triggers)}",
        ]

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
            if messagebox.askyesno(
                "Maps Folder Not Found",
                "Could not auto-detect the game's maps folder.\n\nBrowse for it?",
            ):
                self._browse_folder()
                folder_str = self.config.get("maps_folder")
                if folder_str:
                    maps_folder = Path(folder_str)

        if maps_folder is None:
            return

        try:
            map_path = self.temp_dir / self.current_map_name / f"{self.current_map_name}.map"
            dest = install_map(map_path, maps_folder)
            self._set_status(f"Installed to {dest.name}", COLORS["success"])
            messagebox.showinfo(
                "Installed!",
                f"Map '{self.current_map_name}' has been installed.\n\n"
                f"Location: {dest}\n\n"
                "Launch the game and look for it in Skirmish!",
            )
        except Exception as e:
            messagebox.showerror("Install Error", str(e))

    def _save_as(self):
        if self.current_map is None:
            return
        folder = filedialog.askdirectory(title="Save Map To…")
        if not folder:
            return

        dest = Path(folder) / self.current_map_name
        dest.mkdir(parents=True, exist_ok=True)
        self.current_map.save(dest / f"{self.current_map_name}.map")

        from cnc_zh_map_maker.builder import MapBuilder
        builder = MapBuilder.__new__(MapBuilder)
        builder._width = self.current_map.height_map.width
        builder._height = self.current_map.height_map.height
        builder._base_elevation = 400
        builder._generate_preview_tga(dest / f"{self.current_map_name}.tga")

        self._set_status(f"Saved to {dest}", COLORS["success"])

    def run(self):
        self.root.mainloop()


def _categorize_object(type_name: str) -> str:
    t = type_name.lower()
    if "tree" in t or "bush" in t:
        return "Trees/Vegetation"
    if "rock" in t or "boulder" in t:
        return "Rocks"
    if "civ" in t or "house" in t:
        return "Civilian Buildings"
    if "tech" in t or "oil" in t or "hospital" in t:
        return "Tech Buildings"
    if "supply" in t:
        return "Supply Docks"
    if "barrel" in t or "crate" in t or "fence" in t or "lamp" in t:
        return "Props"
    return "Other"


def main():
    app = MapMakerApp()
    app.run()


if __name__ == "__main__":
    main()
