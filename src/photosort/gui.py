"""Tkinter GUI — native folder pickers on macOS, Windows and Linux."""
from __future__ import annotations

import queue
import threading
from pathlib import Path
from tkinter import END, LEFT, RIGHT, X, BooleanVar, StringVar, Tk, ttk
from tkinter.filedialog import askdirectory
from tkinter.scrolledtext import ScrolledText

from . import organizer

MODE_CHOICES = [
    (organizer.MODE_DATE_LOCATION, "За датою та місцем (рік / місяць / місце) — типово"),
    (organizer.MODE_DATE, "Тільки за датою (рік / місяць)"),
    (organizer.MODE_LOCATION, "Тільки за місцем (місце / рік)"),
]


class App:
    def __init__(self, root: Tk):
        self.root = root
        self.msgs: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None

        root.title("PhotoSort — сортування фотографій")
        root.geometry("720x560")
        root.minsize(600, 460)

        pad = {"padx": 12, "pady": 6}
        frm = ttk.Frame(root)
        frm.pack(fill=X, **pad)

        ttk.Label(frm, text="Вхідна папка (з фото):").grid(row=0, column=0, sticky="w")
        self.src_var = StringVar()
        ttk.Entry(frm, textvariable=self.src_var).grid(row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(frm, text="Обрати…", command=self.pick_src).grid(row=1, column=1)

        ttk.Label(frm, text="Куди складати відсортовані:").grid(row=2, column=0, sticky="w")
        self.dst_var = StringVar()
        ttk.Entry(frm, textvariable=self.dst_var).grid(row=3, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(frm, text="Обрати…", command=self.pick_dst).grid(row=3, column=1)
        frm.columnconfigure(0, weight=1)

        mode_frm = ttk.LabelFrame(root, text="Як сортувати")
        mode_frm.pack(fill=X, **pad)
        self.mode_var = StringVar(value=organizer.MODE_DATE_LOCATION)
        for value, label in MODE_CHOICES:
            ttk.Radiobutton(mode_frm, text=label, value=value, variable=self.mode_var).pack(
                anchor="w", padx=10, pady=2)

        opt_frm = ttk.Frame(root)
        opt_frm.pack(fill=X, **pad)
        self.move_var = BooleanVar(value=False)
        ttk.Checkbutton(opt_frm, text="Переміщувати файли (замість копіювання)",
                        variable=self.move_var).pack(side=LEFT)
        self.net_var = BooleanVar(value=True)
        ttk.Checkbutton(opt_frm, text="Визначати назви місць через інтернет (Nominatim)",
                        variable=self.net_var).pack(side=LEFT, padx=16)

        run_frm = ttk.Frame(root)
        run_frm.pack(fill=X, **pad)
        self.run_btn = ttk.Button(run_frm, text="▶ Почати сортування", command=self.start)
        self.run_btn.pack(side=LEFT)
        self.progress = ttk.Progressbar(run_frm, mode="determinate")
        self.progress.pack(side=RIGHT, fill=X, expand=True, padx=(12, 0))

        self.log_box = ScrolledText(root, height=14, state="disabled", wrap="word")
        self.log_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        root.after(120, self._drain)

    # ---- thread-safe UI updates -------------------------------------------
    def log(self, msg: str):
        self.msgs.put(("log", str(msg)))

    def _progress_cb(self, done: int, total: int):
        self.msgs.put(("progress", (done, total)))

    def _drain(self):
        try:
            while True:
                kind, payload = self.msgs.get_nowait()
                if kind == "log":
                    self._append(payload)
                elif kind == "progress":
                    done, total = payload
                    self.progress["maximum"] = max(total, 1)
                    self.progress["value"] = done * 100 // max(total, 1)
                elif kind == "done":
                    self.run_btn.configure(state="normal", text="▶ Почати сортування")
        except queue.Empty:
            pass
        self.root.after(120, self._drain)

    def _append(self, msg: str):
        self.log_box.configure(state="normal")
        self.log_box.insert(END, msg + "\n")
        self.log_box.see(END)
        self.log_box.configure(state="disabled")

    # ---- actions -----------------------------------------------------------
    def pick_src(self):
        d = askdirectory(title="Оберіть папку з фотографіями",
                         initialdir=self.src_var.get() or str(Path.home()))
        if d:
            self.src_var.set(d)

    def pick_dst(self):
        d = askdirectory(title="Оберіть папку для відсортованих фото",
                         initialdir=self.dst_var.get() or str(Path.home()))
        if d:
            self.dst_var.set(d)

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        src, dst = self.src_var.get().strip(), self.dst_var.get().strip()
        if not src or not Path(src).is_dir():
            self.log("⚠ Оберіть коректну вхідну папку.")
            return
        if not dst:
            self.log("⚠ Оберіть папку призначення.")
            return
        mode, move, net = self.mode_var.get(), self.move_var.get(), self.net_var.get()
        self.run_btn.configure(state="disabled", text="Працюю…")
        self.progress["value"] = 0

        def work():
            try:
                organizer.run(Path(src), Path(dst), mode=mode, move=move,
                              network=net, log=self.log, progress=self._progress_cb)
            except Exception as exc:
                self.log(f"✖ Помилка: {exc}")
            finally:
                self.msgs.put(("done", None))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()


def run_gui():
    root = Tk()
    App(root)
    root.mainloop()
