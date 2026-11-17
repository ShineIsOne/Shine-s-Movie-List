"""
movie_manager.pyw — GUI untuk kelola Movie List & sinkronisasi ke index.html / movielist.json.
Fitur: Pencarian film via TMDB (The Movie Database) API, Tambah dengan dialog skor,
       Editor data leluasa (Judul, Genre, Sutradara, Durasi, Sinopsis, Cover, dll),
       Export otomatis ke index.html & movielist.json, serta Push ke GitHub.
UI: Modern CustomTkinter dark theme — sleek, clean, konsisten dengan anime_manager.pyw.
"""
import customtkinter as ctk
from tkinter import messagebox, filedialog, ttk
import urllib.request, urllib.parse, urllib.error
import json, os, sys, threading, time, re, subprocess, webbrowser

# ── CustomTkinter Global Settings ─────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

SCRIPT_DIR  = os.path.dirname(os.path.abspath(sys.argv[0]))
CONFIG_FILE = os.path.join(SCRIPT_DIR, ".movie_manager_config")

HTML_FILE = ""
JSON_FILE = ""

# ── TMDB Genre Fallback Mapping ────────────────────────────────────────────────
TMDB_GENRES = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy", 80: "Crime",
    99: "Documentary", 18: "Drama", 10751: "Family", 14: "Fantasy", 36: "History",
    27: "Horror", 10402: "Music", 9648: "Mystery", 10749: "Romance",
    878: "Sci-Fi", 10770: "TV Movie", 53: "Thriller", 10752: "War", 37: "Western"
}

# ── Config Loader & Saver ─────────────────────────────────────────────────────
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def set_data_dir(folder):
    global HTML_FILE, JSON_FILE
    HTML_FILE = os.path.join(folder, "index.html")
    JSON_FILE = os.path.join(folder, "movielist.json")

# ── HTML & JSON Sync Helpers ──────────────────────────────────────────────────
def fix_json_string(raw):
    out = []
    in_string = False
    i = 0
    while i < len(raw):
        c = raw[i]
        if c == '\\' and in_string:
            out.append(c); i += 1
            if i < len(raw): out.append(raw[i])
            i += 1; continue
        if c == '"':
            in_string = not in_string; out.append(c)
        elif in_string and c == '\n': out.append('\\n')
        elif in_string and c == '\r': out.append('\\r')
        elif in_string and c == '\t': out.append('\\t')
        else: out.append(c)
        i += 1
    return ''.join(out)

def find_data_marker(html):
    s = html.find("const MOVIE_DATA = [")
    if s == -1:
        return -1, -1
    e = html.find("];\n// ============", s)
    if e == -1:
        e = html.find("];\r\n// ============", s)
    return s, e

def load_from_html():
    if not os.path.exists(HTML_FILE):
        if os.path.exists(JSON_FILE):
            try:
                with open(JSON_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []
    with open(HTML_FILE, "r", encoding="utf-8") as f:
        html = f.read()
    s, e = find_data_marker(html)
    if s == -1 or e == -1:
        if os.path.exists(JSON_FILE):
            try:
                with open(JSON_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []
    raw = html[s + len("const MOVIE_DATA = "):e + 1]
    try:
        return json.loads(fix_json_string(raw))
    except Exception:
        return []

def update_html(data):
    if not os.path.exists(HTML_FILE):
        messagebox.showerror("Error", f"File HTML tidak ditemukan:\n{HTML_FILE}")
        return False
    with open(HTML_FILE, "r", encoding="utf-8") as f:
        html = f.read()
    s, e = find_data_marker(html)
    if s == -1 or e == -1:
        messagebox.showerror("Error", "Marker MOVIE_DATA tidak ditemukan di index.html.")
        return False
    new_html = (html[:s] + "const MOVIE_DATA = " +
                json.dumps(data, ensure_ascii=False, indent=2) + html[e + 1:])
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(new_html)
    return True

def save_json(data):
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ── TMDB API Functions ────────────────────────────────────────────────────────
def tmdb_request(url, api_key):
    headers = {
        "User-Agent": "MovieManager/1.0",
        "Accept": "application/json"
    }
    # Support both Bearer token and standard API key
    if len(api_key) > 50 and not api_key.startswith("http"):
        headers["Authorization"] = f"Bearer {api_key}"
        sep = "&" if "?" in url else "?"
        req_url = url
    else:
        sep = "&" if "?" in url else "?"
        req_url = f"{url}{sep}api_key={urllib.parse.quote(api_key)}"
    
    req = urllib.request.Request(req_url, headers=headers)
    with urllib.request.urlopen(req, timeout=12) as response:
        return json.loads(response.read().decode("utf-8"))

def tmdb_search_movies(query, api_key, language="en-US"):
    if not api_key:
        raise ValueError("TMDB API Key belum diatur. Buka tab Pengaturan untuk memasukkan API Key.")
    
    q = urllib.parse.quote(query)
    url = f"https://api.themoviedb.org/3/search/movie?query={q}&language={language}&include_adult=false"
    try:
        data = tmdb_request(url, api_key)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise RuntimeError("API Key TMDB tidak valid (HTTP 401 Unauthorized).")
        raise RuntimeError(f"Gagal mencari di TMDB (HTTP {e.code}): {e.reason}")
    except Exception as e:
        raise RuntimeError(f"Gagal menghubungi server TMDB: {e}")

    results = []
    for item in data.get("results", [])[:15]:
        genres = [TMDB_GENRES.get(gid, "Movie") for gid in item.get("genre_ids", [])]
        release = item.get("release_date") or ""
        year = int(release[:4]) if len(release) >= 4 and release[:4].isdigit() else None
        poster_path = item.get("poster_path")
        cover_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ""
        
        results.append({
            "tmdb_id": item.get("id"),
            "title": item.get("title") or item.get("original_title") or "Untitled",
            "original_title": item.get("original_title") or "",
            "year": year,
            "vote_average": round(item.get("vote_average", 0), 1),
            "genres": genres,
            "overview": item.get("overview") or "",
            "cover": cover_url,
        })
    return results

def tmdb_get_movie_detail(movie_id, api_key, language="en-US"):
    url = f"https://api.themoviedb.org/3/movie/{movie_id}?language={language}&append_to_response=credits"
    data = tmdb_request(url, api_key)
    
    # If overview is empty, fallback to en-US
    overview = data.get("overview") or ""
    if not overview and language != "en-US":
        try:
            en_data = tmdb_request(f"https://api.themoviedb.org/3/movie/{movie_id}?language=en-US", api_key)
            overview = en_data.get("overview") or ""
        except Exception:
            pass

    # Extract director
    crew = data.get("credits", {}).get("crew", [])
    directors = [m.get("name") for m in crew if m.get("job") == "Director"]
    director = ", ".join(directors) if directors else ""

    # Format runtime in English: e.g. 2h 15m
    runtime_mins = data.get("runtime") or 0
    if runtime_mins >= 60:
        h = runtime_mins // 60
        m = runtime_mins % 60
        runtime_str = f"{h}h {m}m" if m > 0 else f"{h}h"
    elif runtime_mins > 0:
        runtime_str = f"{runtime_mins}m"
    else:
        runtime_str = ""

    # Genres list
    genres = [g.get("name") for g in data.get("genres", [])]
    if not genres:
        genres = ["Movie"]

    release = data.get("release_date") or ""
    year = int(release[:4]) if len(release) >= 4 and release[:4].isdigit() else None
    poster_path = data.get("poster_path")
    cover_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ""

    title = data.get("title") or data.get("original_title") or "Untitled"
    orig_title = data.get("original_title") or ""

    return {
        "tmdb_id": movie_id,
        "title": title,
        "titleEn": orig_title if orig_title != title else "",
        "originalTitle": orig_title,
        "genre": genres,
        "director": director,
        "year": year,
        "runtime": runtime_str,
        "score": round(data.get("vote_average", 0), 1),
        "synopsis": overview,
        "cover": cover_url,
        "tmdb": f"https://www.themoviedb.org/movie/{movie_id}",
    }

# ── Design Tokens ─────────────────────────────────────────────────────────────
C = {
    "bg":           "#0d1117",
    "bg_panel":     "#161b22",
    "bg_card":      "#1c2128",
    "bg_input":     "#21262d",
    "bg_hover":     "#2d333b",
    "border":       "#30363d",
    "border_focus": "#58a6ff",
    "text":         "#e6edf3",
    "text_dim":     "#8b949e",
    "text_faint":   "#484f58",
    "accent":       "#58a6ff",
    "accent_glow":  "#1f6feb",
    "accent_soft":  "#0d2045",
    "gold":         "#e3c343",
    "gold_bright":  "#f0d060",
    "green":        "#238636",
    "red":          "#f85149",
    "heading":      "#79c0ff",
}

FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_SMALL = ("Segoe UI", 9)
FONT_LARGE = ("Segoe UI", 13, "bold")
FONT_HERO  = ("Segoe UI", 15, "bold")

# ── Score Dialog ──────────────────────────────────────────────────────────────
class ScoreDialog(ctk.CTkToplevel):
    def __init__(self, parent, movie_title, default_score=8.0):
        super().__init__(parent)
        self.title("Beri Rating Film")
        self.geometry("420x360")
        self.resizable(False, False)
        self.grab_set()
        self.transient(parent)
        self.result = None
        self.configure(fg_color=C["bg"])

        # Top colored line
        header = ctk.CTkFrame(self, fg_color=C["gold"], height=4, corner_radius=0)
        header.pack(fill="x")

        body = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        body.pack(fill="both", expand=True, padx=24, pady=16)

        ctk.CTkLabel(body, text="Beri Rating Anda untuk Film:", text_color=C["text_dim"],
                     font=FONT_SMALL).pack(anchor="w")
        ctk.CTkLabel(body, text=movie_title, text_color=C["text"],
                     font=FONT_LARGE, wraplength=370, justify="left").pack(anchor="w", pady=(2, 10))

        ctk.CTkFrame(body, fg_color=C["border"], height=1, corner_radius=0).pack(fill="x", pady=(0, 14))

        input_row = ctk.CTkFrame(body, fg_color="transparent")
        input_row.pack(anchor="w")

        self._score_entry = ctk.CTkEntry(
            input_row, width=90, height=38, font=("Segoe UI", 18, "bold"),
            fg_color=C["bg_input"], border_color=C["border"],
            text_color=C["gold_bright"], justify="center"
        )
        self._score_entry.pack(side="left")
        self._score_entry.insert(0, str(default_score))
        self._score_entry.focus_set()
        self._score_entry.select_range(0, "end")

        ctk.CTkLabel(input_row, text=" / 10", text_color=C["text_dim"],
                     font=("Segoe UI", 13, "bold")).pack(side="left", padx=8)

        ctk.CTkLabel(body, text="Rentang skor: 0.1 – 10.0 (contoh: 8 atau 8.5)",
                     text_color=C["text_faint"], font=FONT_SMALL).pack(anchor="w", pady=(6, 2))

        self._err_var = ctk.StringVar(value="")
        ctk.CTkLabel(body, textvariable=self._err_var, text_color=C["red"],
                     font=FONT_SMALL).pack(anchor="w")

        # Quick score buttons
        ctk.CTkLabel(body, text="Pilihan Cepat:", text_color=C["text_dim"],
                     font=FONT_SMALL).pack(anchor="w", pady=(6, 4))
        qrow = ctk.CTkFrame(body, fg_color="transparent")
        qrow.pack(fill="x")
        for s in [7.0, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0]:
            ctk.CTkButton(
                qrow, text=str(s), width=42, height=28, font=FONT_SMALL,
                fg_color=C["bg_input"], hover_color=C["bg_hover"],
                text_color=C["text"], corner_radius=6,
                command=lambda val=s: self._set_quick(val)
            ).pack(side="left", padx=2)

        ctk.CTkFrame(body, fg_color=C["border"], height=1, corner_radius=0).pack(fill="x", pady=14)

        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x")

        ctk.CTkButton(
            btn_row, text="Batal", width=90, height=34, font=FONT,
            fg_color=C["bg_input"], hover_color=C["bg_hover"],
            text_color=C["text_dim"], corner_radius=8,
            command=self.destroy
        ).pack(side="left")

        ctk.CTkButton(
            btn_row, text="✓ Tambahkan ke List", height=34, font=FONT_BOLD,
            fg_color=C["gold"], hover_color="#c2a430",
            text_color="#0d1117", corner_radius=8,
            command=self._confirm
        ).pack(side="right")

        self.bind("<Return>", lambda e: self._confirm())
        self.bind("<Escape>", lambda e: self.destroy())

    def _set_quick(self, val):
        self._score_entry.delete(0, "end")
        self._score_entry.insert(0, str(val))
        self._score_entry.focus_set()

    def _confirm(self):
        val_str = self._score_entry.get().strip().replace(",", ".")
        try:
            val = float(val_str)
            if not (0.0 <= val <= 10.0):
                self._err_var.set("Skor harus berada di antara 0.0 hingga 10.0")
                return
        except ValueError:
            self._err_var.set("Masukkan angka yang valid (misal 8.5)")
            return
        self.result = round(val, 1)
        self.destroy()

# ── Nav Button ────────────────────────────────────────────────────────────────
class NavButton(ctk.CTkButton):
    def __init__(self, parent, text, icon="", command=None):
        super().__init__(
            parent,
            text=f"  {icon}  {text}" if icon else f"  {text}",
            anchor="w",
            height=36,
            font=FONT,
            fg_color="transparent",
            hover_color=C["bg_hover"],
            text_color=C["text_dim"],
            corner_radius=8,
            command=command,
        )
        self._active = False

    def set_active(self, active: bool):
        self._active = active
        if active:
            self.configure(
                fg_color=C["accent_soft"],
                text_color=C["heading"],
                font=FONT_BOLD,
            )
        else:
            self.configure(
                fg_color="transparent",
                text_color=C["text_dim"],
                font=FONT,
            )

# ── Main Application Window ───────────────────────────────────────────────────
class MovieApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Movie List Manager — TMDB")
        self.geometry("1100x740")
        self.minsize(940, 620)
        self.configure(fg_color=C["bg"])

        self._cfg = load_config()
        self.tmdb_api_key = self._cfg.get("tmdb_api_key", "")
        self.tmdb_lang    = self._cfg.get("tmdb_language", "en-US")

        self.movie_data = []
        self._selected_id = None
        self._search_thread = None

        self._build_ui()
        self._apply_treeview_styles()

        # Load root folder
        saved_root = self._cfg.get("root_folder", SCRIPT_DIR)
        if saved_root and os.path.isdir(saved_root):
            self.root_var.set(saved_root)
            set_data_dir(saved_root)
            self.movie_data = load_from_html() or []
            self._refresh_list()
            self._editor_refresh_list()
            self._set_status(f"✓ Folder data aktif: {saved_root}")
        else:
            self.root_var.set(SCRIPT_DIR)
            set_data_dir(SCRIPT_DIR)
            self.movie_data = load_from_html() or []
            self._refresh_list()
            self._editor_refresh_list()

    def _build_ui(self):
        # ── Top Bar ──────────────────────────────────────────────────────────
        topbar = ctk.CTkFrame(self, fg_color=C["bg_panel"], height=52, corner_radius=0)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)

        ctk.CTkLabel(
            topbar, text="🎬  Movie List Manager",
            font=FONT_HERO, text_color=C["text"]
        ).pack(side="left", padx=20, pady=10)

        ctk.CTkLabel(
            topbar, text="TMDB Powered",
            font=FONT_SMALL, text_color=C["gold"]
        ).pack(side="left", padx=4, pady=14)

        sep = ctk.CTkFrame(self, fg_color=C["border"], height=1, corner_radius=0)
        sep.pack(fill="x")

        # ── Body ─────────────────────────────────────────────────────────────
        body = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        body.pack(fill="both", expand=True)

        # Sidebar
        self._sidebar = ctk.CTkFrame(body, fg_color=C["bg_panel"], width=210, corner_radius=0)
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)
        self._build_sidebar()

        sep2 = ctk.CTkFrame(body, fg_color=C["border"], width=1, corner_radius=0)
        sep2.pack(side="left", fill="y")

        # Content Area
        self._content = ctk.CTkFrame(body, fg_color=C["bg"], corner_radius=0)
        self._content.pack(side="left", fill="both", expand=True)

        self._page_manager  = ctk.CTkFrame(self._content, fg_color=C["bg"], corner_radius=0)
        self._page_editor   = ctk.CTkFrame(self._content, fg_color=C["bg"], corner_radius=0)
        self._page_settings = ctk.CTkFrame(self._content, fg_color=C["bg"], corner_radius=0)

        self._build_manager_ui(self._page_manager)
        self._build_editor_ui(self._page_editor)
        self._build_settings_ui(self._page_settings)

        # Status Bar
        ctk.CTkFrame(self, fg_color=C["border"], height=1, corner_radius=0).pack(fill="x", side="bottom")
        sbar = ctk.CTkFrame(self, fg_color=C["bg_panel"], height=28, corner_radius=0)
        sbar.pack(fill="x", side="bottom")
        sbar.pack_propagate(False)

        self._status_var = ctk.StringVar(value="Siap.")
        self._count_var  = ctk.StringVar(value="0 Film")
        ctk.CTkLabel(sbar, textvariable=self._status_var, text_color=C["text_dim"],
                     font=FONT_SMALL, anchor="w").pack(side="left", padx=14, fill="y")
        ctk.CTkLabel(sbar, textvariable=self._count_var, text_color=C["text_faint"],
                     font=FONT_SMALL, anchor="e").pack(side="right", padx=14, fill="y")

        self._show_page("manager")

    def _set_status(self, msg):
        self._status_var.set(msg)

    def _apply_treeview_styles(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("Treeview",
                    background=C["bg_card"], foreground=C["text"],
                    fieldbackground=C["bg_card"], font=FONT,
                    rowheight=32, borderwidth=0)
        s.configure("Treeview.Heading",
                    background=C["bg_input"], foreground=C["heading"],
                    font=("Segoe UI", 9, "bold"), relief="flat", padding=[8, 6])
        s.map("Treeview",
              background=[("selected", C["accent_soft"])],
              foreground=[("selected", C["accent"])])
        s.map("Treeview.Heading", background=[("active", C["bg_hover"])])
        s.configure("Vertical.TScrollbar",
                    background=C["bg_input"], troughcolor=C["bg_card"],
                    arrowcolor=C["text_dim"], borderwidth=0, relief="flat", width=8)

    # ─────────────────────────────────────────────────────────────────────────
    # Sidebar
    # ─────────────────────────────────────────────────────────────────────────
    def _build_sidebar(self):
        sb = self._sidebar

        ctk.CTkLabel(sb, text="NAVIGASI", text_color=C["text_faint"],
                     font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=16, pady=(16, 4))

        self._nav_btns = {}
        pages = [("manager", "🎬", "Manager Film"),
                 ("editor", "✏️", "Editor Data"),
                 ("settings", "⚙️", "Pengaturan")]
        for key, icon, name in pages:
            btn = NavButton(sb, name, icon, command=lambda k=key: self._show_page(k))
            btn.pack(fill="x", padx=8, pady=2)
            self._nav_btns[key] = btn

        ctk.CTkFrame(sb, fg_color=C["border"], height=1, corner_radius=0).pack(fill="x", padx=12, pady=12)

        # Folder data selection
        ctk.CTkLabel(sb, text="FOLDER DATA", text_color=C["text_faint"],
                     font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=16, pady=(0, 4))

        fi = ctk.CTkFrame(sb, fg_color="transparent")
        fi.pack(fill="x", padx=10)

        self.root_var = ctk.StringVar()
        self._folder_entry = ctk.CTkEntry(
            fi, textvariable=self.root_var, height=30, font=FONT_SMALL,
            fg_color=C["bg_input"], border_color=C["border"], text_color=C["text_dim"],
            placeholder_text="Pilih folder..."
        )
        self._folder_entry.pack(fill="x", pady=(0, 6))

        row = ctk.CTkFrame(fi, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkButton(
            row, text="📂 Browse", height=28, font=FONT_SMALL,
            fg_color=C["bg_input"], hover_color=C["bg_hover"],
            text_color=C["text_dim"], corner_radius=6,
            command=self._browse_folder
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(
            row, text="↺", width=30, height=28, font=FONT_SMALL,
            fg_color=C["bg_input"], hover_color=C["bg_hover"],
            text_color=C["text_dim"], corner_radius=6,
            command=self._reload_folder
        ).pack(side="left")

    def _show_page(self, page):
        self._page_manager.pack_forget()
        self._page_editor.pack_forget()
        self._page_settings.pack_forget()
        for k, btn in self._nav_btns.items():
            btn.set_active(k == page)
        if page == "manager":
            self._page_manager.pack(fill="both", expand=True)
        elif page == "editor":
            self._page_editor.pack(fill="both", expand=True)
            self._editor_refresh_list()
        elif page == "settings":
            self._page_settings.pack(fill="both", expand=True)

    # ─────────────────────────────────────────────────────────────────────────
    # Page 1: Manager UI (Search & List)
    # ─────────────────────────────────────────────────────────────────────────
    def _build_manager_ui(self, parent):
        # Left Panel (Search & Actions)
        left = ctk.CTkFrame(parent, fg_color=C["bg_panel"], width=330, corner_radius=0)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        sep = ctk.CTkFrame(parent, fg_color=C["border"], width=1, corner_radius=0)
        sep.pack(side="left", fill="y")

        # Right Panel (Movie Table)
        right = ctk.CTkFrame(parent, fg_color=C["bg"], corner_radius=0)
        right.pack(side="left", fill="both", expand=True)

        self._build_search_panel(left)
        self._build_list_panel(right)

    def _build_search_panel(self, parent):
        inner = ctk.CTkFrame(parent, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=14, pady=12)

        ctk.CTkLabel(inner, text="🔍  Cari di TMDB", font=FONT_LARGE,
                     text_color=C["heading"]).pack(anchor="w", pady=(2, 8))

        self.search_entry = ctk.CTkEntry(
            inner, height=36, font=FONT,
            placeholder_text="Ketik judul film...",
            fg_color=C["bg_input"], border_color=C["border"],
            border_width=1, corner_radius=8, text_color=C["text"]
        )
        self.search_entry.pack(fill="x")
        self.search_entry.bind("<Return>", lambda e: self._do_search())

        ctk.CTkButton(
            inner, text="🔎  Cari Film", height=36, font=FONT_BOLD,
            fg_color=C["accent_glow"], hover_color="#1158b8",
            corner_radius=8, command=self._do_search
        ).pack(fill="x", pady=(8, 0))

        ctk.CTkFrame(inner, fg_color=C["border"], height=1, corner_radius=0).pack(fill="x", pady=10)

        # Action Buttons
        ctk.CTkButton(
            inner, text="🗑  Hapus Terpilih", height=32, font=FONT_SMALL,
            fg_color=C["red"], hover_color="#b03a33",
            corner_radius=8, command=self._delete_selected
        ).pack(fill="x", pady=(0, 6))

        ctk.CTkButton(
            inner, text="💾  Simpan & Update HTML", height=36, font=FONT_BOLD,
            fg_color=C["gold"], hover_color="#c2a430",
            text_color="#0d1117", corner_radius=8,
            command=self._save_and_update
        ).pack(fill="x")

        ctk.CTkButton(
            inner, text="🐙  Push ke GitHub", height=32, font=FONT_SMALL,
            fg_color=C["green"], hover_color="#1a6128",
            text_color="#ffffff", corner_radius=8,
            command=self._push_github
        ).pack(fill="x", pady=(6, 0))

        ctk.CTkFrame(inner, fg_color=C["border"], height=1, corner_radius=0).pack(fill="x", pady=10)

        ctk.CTkLabel(inner, text="HASIL PENCARIAN", text_color=C["text_faint"],
                     font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 4))

        self.results_scroll = ctk.CTkScrollableFrame(
            inner, fg_color="transparent", corner_radius=0
        )
        self.results_scroll.pack(fill="both", expand=True)

        self._show_results_placeholder("Ketik judul film di atas lalu tekan Cari.")

    def _show_results_placeholder(self, text):
        for w in self.results_scroll.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.results_scroll, text=text, text_color=C["text_faint"],
                     font=FONT_SMALL, wraplength=280, justify="center").pack(pady=30)

    def _build_list_panel(self, parent):
        inner = ctk.CTkFrame(parent, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=16, pady=12)

        ctk.CTkLabel(inner, text="🎥  Daftar Film Tersimpan", font=FONT_LARGE,
                     text_color=C["heading"]).pack(anchor="w", pady=(0, 10))

        tree_wrap = ctk.CTkFrame(inner, fg_color=C["bg_card"],
                                 border_color=C["border"], border_width=1, corner_radius=8)
        tree_wrap.pack(fill="both", expand=True)

        cols = ("judul", "genre", "tahun", "durasi", "sutradara", "skor")
        self.tree = ttk.Treeview(tree_wrap, columns=cols, height=20,
                                 selectmode="browse", show="headings")
        
        col_defs = [
            ("judul", 250, "w", "Judul Film"),
            ("genre", 180, "w", "Genre"),
            ("tahun", 70, "center", "Tahun"),
            ("durasi", 80, "center", "Durasi"),
            ("sutradara", 160, "w", "Sutradara"),
            ("skor", 70, "center", "★ Skor"),
        ]
        for col, w, anc, text in col_defs:
            self.tree.column(col, width=w, anchor=anc, minwidth=50)
            self.tree.heading(col, text=text)

        sb = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.tree.bind("<Double-1>", lambda e: self._on_tree_double_click())

    # ─────────────────────────────────────────────────────────────────────────
    # Page 2: Editor UI
    # ─────────────────────────────────────────────────────────────────────────
    def _build_editor_ui(self, parent):
        inner = ctk.CTkFrame(parent, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=16, pady=14)

        ctk.CTkLabel(inner, text="✏️  Editor Data Film", font=FONT_LARGE,
                     text_color=C["heading"]).pack(anchor="w", pady=(0, 10))

        content_row = ctk.CTkFrame(inner, fg_color="transparent")
        content_row.pack(fill="both", expand=True)

        # Left: List of movies
        left_frame = ctk.CTkFrame(content_row, fg_color="transparent", width=290)
        left_frame.pack(side="left", fill="y", padx=(0, 12))
        left_frame.pack_propagate(False)

        ctk.CTkLabel(left_frame, text="PILIH FILM", text_color=C["text_faint"],
                     font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 4))

        self._editor_filter_entry = ctk.CTkEntry(
            left_frame, height=32, font=FONT_SMALL,
            placeholder_text="Filter daftar...",
            fg_color=C["bg_input"], border_color=C["border"], text_color=C["text"]
        )
        self._editor_filter_entry.pack(fill="x", pady=(0, 6))
        self._editor_filter_entry.bind("<KeyRelease>", lambda e: self._editor_filter_list())

        lw = ctk.CTkFrame(left_frame, fg_color=C["bg_card"],
                          border_color=C["border"], border_width=1, corner_radius=8)
        lw.pack(fill="both", expand=True)

        self._editor_tree = ttk.Treeview(lw, columns=("title", "year"), show="headings", selectmode="browse")
        self._editor_tree.heading("title", text="Judul")
        self._editor_tree.heading("year", text="Tahun")
        self._editor_tree.column("title", width=190, anchor="w")
        self._editor_tree.column("year", width=60, anchor="center")

        esb = ttk.Scrollbar(lw, orient="vertical", command=self._editor_tree.yview)
        self._editor_tree.configure(yscrollcommand=esb.set)
        self._editor_tree.pack(side="left", fill="both", expand=True)
        esb.pack(side="right", fill="y")
        self._editor_tree.bind("<<TreeviewSelect>>", self._on_editor_select)

        # Right: Form
        right_frame = ctk.CTkFrame(content_row, fg_color="transparent")
        right_frame.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(right_frame, text="DETAIL & EDIT", text_color=C["text_faint"],
                     font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 4))

        form_card = ctk.CTkScrollableFrame(right_frame, fg_color=C["bg_card"],
                                           border_color=C["border"], border_width=1, corner_radius=8)
        form_card.pack(fill="both", expand=True)

        self._edit_fields = {}
        fields = [
            ("title", "Judul Film:"),
            ("titleEn", "Judul Bahasa Inggris:"),
            ("originalTitle", "Judul Asli (Original):"),
            ("genre", "Genre (pisahkan dengan koma):"),
            ("director", "Sutradara:"),
            ("year", "Tahun Rilis:"),
            ("runtime", "Durasi (contoh: 2j 15m):"),
            ("score", "Skor Rating (0.1 - 10.0):"),
            ("cover", "Link Poster / Cover (URL):"),
            ("tmdb", "Link TMDB:"),
        ]

        for key, label in fields:
            f_row = ctk.CTkFrame(form_card, fg_color="transparent")
            f_row.pack(fill="x", padx=14, pady=4)
            ctk.CTkLabel(f_row, text=label, text_color=C["text_dim"],
                         font=FONT_SMALL, width=190, anchor="w").pack(side="left")
            entry = ctk.CTkEntry(
                f_row, height=30, font=FONT_SMALL,
                fg_color=C["bg_input"], border_color=C["border"], text_color=C["text"]
            )
            entry.pack(side="left", fill="x", expand=True)
            self._edit_fields[key] = entry

        # Synopsis field
        syn_row = ctk.CTkFrame(form_card, fg_color="transparent")
        syn_row.pack(fill="x", padx=14, pady=6)
        ctk.CTkLabel(syn_row, text="Sinopsis:", text_color=C["text_dim"],
                     font=FONT_SMALL).pack(anchor="w")
        self._edit_synopsis = ctk.CTkTextbox(
            syn_row, height=100, font=FONT_SMALL,
            fg_color=C["bg_input"], border_color=C["border"], text_color=C["text"]
        )
        self._edit_synopsis.pack(fill="x", pady=(4, 0))

        # Bottom buttons for Editor
        btn_row = ctk.CTkFrame(right_frame, fg_color="transparent")
        btn_row.pack(fill="x", pady=(10, 0))

        ctk.CTkButton(
            btn_row, text="💾 Simpan Perubahan", height=36, font=FONT_BOLD,
            fg_color=C["gold"], hover_color="#c2a430",
            text_color="#0d1117", corner_radius=8,
            command=self._editor_save
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="🗑 Hapus Film", height=36, font=FONT_SMALL,
            fg_color=C["red"], hover_color="#b03a33",
            corner_radius=8, command=self._editor_delete
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="🌐 Buka TMDB", height=36, font=FONT_SMALL,
            fg_color=C["bg_input"], hover_color=C["bg_hover"],
            text_color=C["text_dim"], corner_radius=8,
            command=self._editor_open_tmdb
        ).pack(side="left")

    # ─────────────────────────────────────────────────────────────────────────
    # Page 3: Settings UI
    # ─────────────────────────────────────────────────────────────────────────
    def _build_settings_ui(self, parent):
        inner = ctk.CTkFrame(parent, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=24, pady=16)

        ctk.CTkLabel(inner, text="⚙️  Pengaturan TMDB API", font=FONT_LARGE,
                     text_color=C["heading"]).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(inner, text="Konfigurasi API Key The Movie Database untuk fitur pencarian otomatis.",
                     font=FONT_SMALL, text_color=C["text_dim"]).pack(anchor="w", pady=(0, 16))

        card = ctk.CTkFrame(inner, fg_color=C["bg_card"],
                            border_color=C["border"], border_width=1, corner_radius=8)
        card.pack(fill="x", pady=(0, 14))

        ci = ctk.CTkFrame(card, fg_color="transparent")
        ci.pack(fill="x", padx=18, pady=16)

        # TMDB API Key Entry
        ctk.CTkLabel(ci, text="TMDB API Key (v3 auth / Bearer Read Token):",
                     text_color=C["text_dim"], font=FONT_SMALL).pack(anchor="w")

        key_row = ctk.CTkFrame(ci, fg_color="transparent")
        key_row.pack(fill="x", pady=(4, 10))

        self._tmdb_key_entry = ctk.CTkEntry(
            key_row, height=36, font=FONT,
            placeholder_text="Masukkan API Key TMDB di sini...",
            fg_color=C["bg_input"], border_color=C["border"], text_color=C["text"],
            show="*"
        )
        self._tmdb_key_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        if self.tmdb_api_key:
            self._tmdb_key_entry.insert(0, self.tmdb_api_key)

        self._show_key_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            key_row, text="Lihat", variable=self._show_key_var,
            font=FONT_SMALL, text_color=C["text_dim"], width=60,
            command=lambda: self._tmdb_key_entry.configure(show="" if self._show_key_var.get() else "*")
        ).pack(side="left")

        # Language option
        ctk.CTkLabel(ci, text="Bahasa Hasil Pencarian TMDB:",
                     text_color=C["text_dim"], font=FONT_SMALL).pack(anchor="w", pady=(4, 2))
        self._lang_menu = ctk.CTkOptionMenu(
            ci, values=["en-US (English)", "id-ID (Bahasa Indonesia)"],
            font=FONT_SMALL, fg_color=C["bg_input"], button_color=C["border"],
            text_color=C["text"]
        )
        self._lang_menu.pack(anchor="w", pady=(0, 14))
        if "id" in self.tmdb_lang:
            self._lang_menu.set("id-ID (Bahasa Indonesia)")
        else:
            self._lang_menu.set("en-US (English)")

        # Test & Save buttons
        btn_row = ctk.CTkFrame(ci, fg_color="transparent")
        btn_row.pack(fill="x", pady=(4, 0))

        ctk.CTkButton(
            btn_row, text="🧪 Uji Koneksi API", height=34, font=FONT,
            fg_color=C["bg_input"], hover_color=C["bg_hover"],
            text_color=C["text_dim"], corner_radius=8,
            command=self._test_tmdb_key
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="💾 Simpan Pengaturan", height=34, font=FONT_BOLD,
            fg_color=C["gold"], hover_color="#c2a430",
            text_color="#0d1117", corner_radius=8,
            command=self._save_settings
        ).pack(side="left")

        # Instruction Guide
        info_card = ctk.CTkFrame(inner, fg_color=C["bg_card"],
                                 border_color=C["border"], border_width=1, corner_radius=8)
        info_card.pack(fill="x")
        ic = ctk.CTkFrame(info_card, fg_color="transparent")
        ic.pack(fill="x", padx=18, pady=16)

        ctk.CTkLabel(ic, text="💡 Cara Mendapatkan TMDB API Key Gratis:",
                     font=FONT_BOLD, text_color=C["heading"]).pack(anchor="w", pady=(0, 6))

        instructions = (
            "1. Buka situs TMDB di https://www.themoviedb.org dan daftar / login akun.\n"
            "2. Masuk ke Settings > API (https://www.themoviedb.org/settings/api).\n"
            "3. Klik 'Create' lalu pilih 'Developer' untuk membuat API Key gratis.\n"
            "4. Salin 'API Key' (v3 auth) atau 'API Read Access Token' (v4), lalu tempel di atas.\n"
            "5. Klik 'Simpan Pengaturan'."
        )
        ctk.CTkLabel(ic, text=instructions, font=FONT_SMALL, text_color=C["text_dim"],
                     justify="left").pack(anchor="w", pady=(0, 10))

        ctk.CTkButton(
            ic, text="🌐 Buka Halaman API TMDB", height=30, font=FONT_SMALL,
            fg_color=C["bg_input"], hover_color=C["bg_hover"],
            text_color=C["accent"], corner_radius=6,
            command=lambda: webbrowser.open("https://www.themoviedb.org/settings/api")
        ).pack(anchor="w")

    # ─────────────────────────────────────────────────────────────────────────
    # Search Logic
    # ─────────────────────────────────────────────────────────────────────────
    def _do_search(self):
        query = self.search_entry.get().strip()
        if not query:
            return
        if not self.tmdb_api_key:
            messagebox.showwarning(
                "TMDB API Key Kosong",
                "Silakan masukkan TMDB API Key Anda di tab Pengaturan (⚙️) terlebih dahulu."
            )
            self._show_page("settings")
            return

        self._show_results_placeholder("⏳ Sedang mencari film di TMDB...")
        self._set_status(f"Mencari '{query}' di TMDB...")

        def run():
            try:
                lang = "id-ID" if "id" in self.tmdb_lang else "en-US"
                results = tmdb_search_movies(query, self.tmdb_api_key, language=lang)
                self.after(0, lambda: self._render_search_results(results))
            except Exception as e:
                self.after(0, lambda: self._on_search_error(str(e)))

        threading.Thread(target=run, daemon=True).start()

    def _on_search_error(self, err_msg):
        self._show_results_placeholder(f"❌ Error:\n{err_msg}")
        self._set_status("Pencarian gagal.")

    def _render_search_results(self, results):
        for w in self.results_scroll.winfo_children():
            w.destroy()

        if not results:
            self._show_results_placeholder("Tidak ada film yang cocok dengan pencarian.")
            self._set_status("Tidak ada hasil.")
            return

        self._set_status(f"Ditemukan {len(results)} hasil film.")

        for item in results:
            card = ctk.CTkFrame(
                self.results_scroll, fg_color=C["bg_card"],
                border_color=C["border"], border_width=1, corner_radius=8
            )
            card.pack(fill="x", pady=4, padx=2)

            body = ctk.CTkFrame(card, fg_color="transparent")
            body.pack(fill="x", padx=10, pady=8)

            title_row = ctk.CTkFrame(body, fg_color="transparent")
            title_row.pack(fill="x")

            title_str = item["title"]
            if item.get("year"):
                title_str += f" ({item['year']})"

            ctk.CTkLabel(title_row, text=title_str, text_color=C["text"],
                         font=FONT_BOLD, wraplength=280, justify="left", anchor="w").pack(side="left", fill="x", expand=True)

            if item.get("vote_average"):
                ctk.CTkLabel(title_row, text=f"★ {item['vote_average']}",
                             text_color=C["gold_bright"], font=FONT_SMALL).pack(side="right")

            if item.get("original_title") and item.get("original_title") != item.get("title"):
                ctk.CTkLabel(body, text=item["original_title"], text_color=C["text_dim"],
                             font=FONT_SMALL, wraplength=280, justify="left").pack(anchor="w")

            if item.get("genres"):
                g_str = ", ".join(item["genres"][:3])
                ctk.CTkLabel(body, text=g_str, text_color=C["text_faint"],
                             font=FONT_SMALL).pack(anchor="w", pady=(2, 0))

            if item.get("overview"):
                ov = item["overview"][:120] + ("..." if len(item["overview"]) > 120 else "")
                ctk.CTkLabel(body, text=ov, text_color=C["text_dim"],
                             font=FONT_SMALL, wraplength=280, justify="left").pack(anchor="w", pady=(3, 6))

            ctk.CTkButton(
                body, text="+ Tambahkan ke List", height=28, font=FONT_SMALL,
                fg_color=C["accent_glow"], hover_color="#1158b8", corner_radius=6,
                command=lambda mid=item["tmdb_id"], mtitle=item["title"], mscore=item.get("vote_average", 8.0):
                    self._on_add_movie_clicked(mid, mtitle, mscore)
            ).pack(fill="x", pady=(4, 0))

    def _on_add_movie_clicked(self, movie_id, movie_title, default_score):
        # Open score rating dialog
        dlg = ScoreDialog(self, movie_title, default_score=default_score or 8.0)
        self.wait_window(dlg)
        if dlg.result is None:
            return
        user_score = dlg.result

        self._set_status(f"Mengambil detail lengkap film '{movie_title}'...")

        def fetch_and_add():
            try:
                lang = "id-ID" if "id" in self.tmdb_lang else "en-US"
                detail = tmdb_get_movie_detail(movie_id, self.tmdb_api_key, language=lang)
                detail["id"] = f"id_{int(time.time()*1000)}"
                detail["score"] = user_score
                detail["emoji"] = "🎬"
                detail["addedAt"] = int(time.time() * 1000)

                self.movie_data.insert(0, detail)
                self.after(0, lambda: self._finish_add(detail))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Gagal Menambahkan Film", f"Error: {e}"))

        threading.Thread(target=fetch_and_add, daemon=True).start()

    def _finish_add(self, movie):
        self._refresh_list()
        self._editor_refresh_list()
        self._save_and_update(silent=True)
        self._set_status(f"✓ Berhasil ditambahkan: {movie.get('title')}")
        messagebox.showinfo("Sukses", f"Film '{movie.get('title')}' berhasil ditambahkan ke list!")

    # ─────────────────────────────────────────────────────────────────────────
    # Table & List Management
    # ─────────────────────────────────────────────────────────────────────────
    def _refresh_list(self):
        for row in self.tree.get_children():
            self.tree.delete(row)

        for m in self.movie_data:
            genres_str = ", ".join(m.get("genre", [])) if isinstance(m.get("genre"), list) else str(m.get("genre", ""))
            score_str = f"★ {m.get('score', 0)}" if m.get("score") else "—"
            self.tree.insert(
                "", "end", iid=m.get("id"),
                values=(
                    m.get("title", ""),
                    genres_str,
                    m.get("year", "—"),
                    m.get("runtime", "—"),
                    m.get("director", "—"),
                    score_str
                )
            )
        self._count_var.set(f"{len(self.movie_data)} Film")

    def _delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Info", "Pilih film pada tabel yang ingin dihapus.")
            return
        movie_id = sel[0]
        movie = next((m for m in self.movie_data if m.get("id") == movie_id), None)
        title = movie.get("title", "Film") if movie else "Film"

        if not messagebox.askyesno("Konfirmasi Hapus", f"Yakin ingin menghapus '{title}' dari list?"):
            return

        self.movie_data = [m for m in self.movie_data if m.get("id") != movie_id]
        self._refresh_list()
        self._editor_refresh_list()
        self._save_and_update(silent=True)
        self._set_status(f"Dihapus: {title}")

    def _on_tree_double_click(self):
        sel = self.tree.selection()
        if not sel:
            return
        movie_id = sel[0]
        self._show_page("editor")
        self._editor_tree.selection_set(movie_id)
        self._editor_tree.see(movie_id)
        self._on_editor_select()

    def _save_and_update(self, silent=False):
        ok = update_html(self.movie_data)
        save_json(self.movie_data)
        if ok and not silent:
            self._set_status("✓ index.html dan movielist.json berhasil diperbarui.")
            messagebox.showinfo("Berhasil", "Data film berhasil disimpan dan index.html telah diperbarui!")

    def _push_github(self):
        folder = self.root_var.get()
        if not folder or not os.path.isdir(folder):
            messagebox.showerror("Error", "Folder git tidak valid.")
            return
        
        self._save_and_update(silent=True)
        self._set_status("Sedang push ke GitHub...")

        def run_git():
            try:
                subprocess.run(["git", "add", "."], cwd=folder, check=True)
                commit = subprocess.run(["git", "commit", "-m", "Update movie list via Movie Manager"],
                                        cwd=folder, capture_output=True, text=True)
                push = subprocess.run(["git", "push"], cwd=folder, capture_output=True, text=True)
                if push.returncode == 0:
                    self.after(0, lambda: messagebox.showinfo("GitHub", "✓ Berhasil push ke GitHub!"))
                    self.after(0, lambda: self._set_status("✓ Berhasil push ke GitHub!"))
                else:
                    err = push.stderr or push.stdout
                    self.after(0, lambda: messagebox.showerror("Git Push Gagal", err[:300]))
                    self.after(0, lambda: self._set_status("Git push gagal."))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Git Error", str(e)))

        threading.Thread(target=run_git, daemon=True).start()

    # ─────────────────────────────────────────────────────────────────────────
    # Editor Logic
    # ─────────────────────────────────────────────────────────────────────────
    def _editor_refresh_list(self):
        filter_txt = self._editor_filter_entry.get().lower().strip()
        for row in self._editor_tree.get_children():
            self._editor_tree.delete(row)

        for m in self.movie_data:
            title = m.get("title", "")
            if filter_txt and filter_txt not in title.lower():
                continue
            self._editor_tree.insert("", "end", iid=m.get("id"), values=(title, m.get("year", "—")))

    def _editor_filter_list(self):
        self._editor_refresh_list()

    def _on_editor_select(self, event=None):
        sel = self._editor_tree.selection()
        if not sel:
            return
        movie_id = sel[0]
        self._selected_id = movie_id
        movie = next((m for m in self.movie_data if m.get("id") == movie_id), None)
        if not movie:
            return

        for k, entry in self._edit_fields.items():
            entry.delete(0, "end")
            val = movie.get(k, "")
            if isinstance(val, list):
                val = ", ".join(val)
            entry.insert(0, str(val) if val is not None else "")

        self._edit_synopsis.delete("1.0", "end")
        self._edit_synopsis.insert("1.0", movie.get("synopsis", ""))

    def _editor_save(self):
        if not self._selected_id:
            messagebox.showinfo("Info", "Pilih film yang ingin diedit terlebih dahulu.")
            return

        movie = next((m for m in self.movie_data if m.get("id") == self._selected_id), None)
        if not movie:
            return

        movie["title"] = self._edit_fields["title"].get().strip()
        movie["titleEn"] = self._edit_fields["titleEn"].get().strip()
        movie["originalTitle"] = self._edit_fields["originalTitle"].get().strip()

        # Parse genres
        raw_genres = self._edit_fields["genre"].get()
        movie["genre"] = [g.strip() for g in raw_genres.split(",") if g.strip()]

        movie["director"] = self._edit_fields["director"].get().strip()

        y_str = self._edit_fields["year"].get().strip()
        movie["year"] = int(y_str) if y_str.isdigit() else None

        movie["runtime"] = self._edit_fields["runtime"].get().strip()

        try:
            movie["score"] = round(float(self._edit_fields["score"].get().strip().replace(",", ".")), 1)
        except Exception:
            pass

        movie["cover"] = self._edit_fields["cover"].get().strip()
        movie["tmdb"] = self._edit_fields["tmdb"].get().strip()
        movie["synopsis"] = self._edit_synopsis.get("1.0", "end-1c").strip()

        self._save_and_update(silent=True)
        self._refresh_list()
        self._editor_refresh_list()
        self._set_status(f"✓ Perubahan tersimpan: {movie.get('title')}")
        messagebox.showinfo("Tersimpan", "Perubahan data film berhasil disimpan!")

    def _editor_delete(self):
        if not self._selected_id:
            return
        movie = next((m for m in self.movie_data if m.get("id") == self._selected_id), None)
        if not movie:
            return
        if not messagebox.askyesno("Hapus", f"Hapus film '{movie.get('title')}'?"):
            return
        self.movie_data = [m for m in self.movie_data if m.get("id") != self._selected_id]
        self._selected_id = None
        for entry in self._edit_fields.values():
            entry.delete(0, "end")
        self._edit_synopsis.delete("1.0", "end")
        self._save_and_update(silent=True)
        self._refresh_list()
        self._editor_refresh_list()

    def _editor_open_tmdb(self):
        url = self._edit_fields["tmdb"].get().strip()
        if url:
            webbrowser.open(url)
        else:
            messagebox.showinfo("Info", "Link TMDB belum ada untuk film ini.")

    # ─────────────────────────────────────────────────────────────────────────
    # Settings & Folder Management
    # ─────────────────────────────────────────────────────────────────────────
    def _test_tmdb_key(self):
        key = self._tmdb_key_entry.get().strip()
        if not key:
            messagebox.showwarning("Peringatan", "Masukkan TMDB API Key terlebih dahulu.")
            return

        self._set_status("Menguji koneksi TMDB API...")

        def run_test():
            try:
                # Call TMDB configuration endpoint
                res = tmdb_request("https://api.themoviedb.org/3/configuration", key)
                if "images" in res:
                    self.after(0, lambda: messagebox.showinfo("Sukses!", "✓ API Key TMDB valid dan terhubung dengan baik!"))
                    self.after(0, lambda: self._set_status("✓ Koneksi TMDB API berhasil."))
                else:
                    self.after(0, lambda: messagebox.showerror("Gagal", "Respons tidak dikenal dari TMDB."))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Koneksi Gagal", f"Gagal validasi API Key TMDB:\n{e}"))
                self.after(0, lambda: self._set_status("Koneksi TMDB API gagal."))

        threading.Thread(target=run_test, daemon=True).start()

    def _save_settings(self):
        key = self._tmdb_key_entry.get().strip()
        lang_sel = self._lang_menu.get()
        lang = "en-US" if "en-US" in lang_sel else "id-ID"

        self.tmdb_api_key = key
        self.tmdb_lang = lang

        self._cfg["tmdb_api_key"] = key
        self._cfg["tmdb_language"] = lang
        save_config(self._cfg)

        self._set_status("✓ Pengaturan tersimpan.")
        messagebox.showinfo("Pengaturan", "Pengaturan TMDB berhasil disimpan!")

    def _browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.root_var.get() or SCRIPT_DIR)
        if folder:
            self.root_var.set(folder)
            self._cfg["root_folder"] = folder
            save_config(self._cfg)
            set_data_dir(folder)
            self.movie_data = load_from_html() or []
            self._refresh_list()
            self._editor_refresh_list()
            self._set_status(f"Folder data dimuat: {folder}")

    def _reload_folder(self):
        folder = self.root_var.get()
        if folder and os.path.isdir(folder):
            set_data_dir(folder)
            self.movie_data = load_from_html() or []
            self._refresh_list()
            self._editor_refresh_list()
            self._set_status(f"Data dimuat ulang dari {folder}")


if __name__ == "__main__":
    app = MovieApp()
    app.mainloop()
