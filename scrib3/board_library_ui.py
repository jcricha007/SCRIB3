"""Thumbnail browser for recent artwork, reusable elements, templates and recovery."""
from datetime import datetime
from pathlib import Path
import sqlite3
import tkinter as tk
from tkinter import ttk

from .board import load_board


class LibraryWindow:
    def __init__(self, editor, kind):
        self.editor = editor
        self.library = editor.studio.library
        self.window = tk.Toplevel(editor.root)
        self.window.title("SCRIB3 | Board library")
        self.window.geometry("650x480")
        panel = ttk.Frame(self.window, padding=12)
        panel.pack(fill="both", expand=True)
        panel.rowconfigure(1, weight=1)
        panel.columnconfigure(0, weight=1)
        self.kind = tk.StringVar(value=kind)
        tabs = ttk.Frame(panel)
        tabs.grid(row=0, columnspan=2, sticky="w", pady=(0, 6))
        for label in ("Boards", "Elements", "Templates", "Recovery"):
            ttk.Radiobutton(tabs, text=label, value=label, variable=self.kind,
                            command=self.refresh).pack(side="left", padx=(0, 8))
        ttk.Style(self.window).configure("BoardLibrary.Treeview", rowheight=82)
        self.list = ttk.Treeview(panel, style="BoardLibrary.Treeview", show="tree", selectmode="browse")
        self.list.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(panel, command=self.list.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.list.configure(yscrollcommand=scroll.set)
        self.list.bind("<Double-1>", lambda _: self.open())
        self.list.bind("<Return>", lambda _: self.open())
        self.list.bind("<<TreeviewSelect>>", self.selection)
        self.status = tk.StringVar()
        ttk.Label(panel, textvariable=self.status, wraplength=490).grid(row=2, columnspan=2, sticky="w", pady=5)
        self.action = ttk.Button(panel, style="Primary.TButton", command=self.open)
        self.action.grid(row=3, columnspan=2, sticky="e")
        self.refresh()

    def refresh(self):
        kind = self.kind.get()
        self.action.configure(text={"Boards":"Open board", "Elements":"Insert element",
                                    "Templates":"Use template", "Recovery":"Restore unsaved copy"}[kind])
        self.list.delete(*self.list.get_children())
        self.rows, self.images = {}, []
        self.action.state(["disabled"])
        try:
            for entry in self.library.entries(kind):
                image = tk.PhotoImage(master=self.window, data=entry.image)
                self.images.append(image)
                label = entry.name
                if kind == "Recovery":
                    label += "   " + datetime.fromtimestamp(entry.updated / 1e9).strftime("%b %d, %H:%M")
                iid = self.list.insert("", "end", text=label, image=image)
                self.rows[iid] = entry
            self.status.set(f"{len(self.rows)} item(s)" if self.rows else {
                "Boards":"Open or save a board to add it here.",
                "Elements":"Save a selection as an element to reuse it on another board.",
                "Templates":"Save a sheet template to reuse its frame and title block.",
                "Recovery":"No interrupted edits to recover."}[kind])
        except (OSError, ValueError, sqlite3.Error) as err:
            self.status.set(str(err))

    def selection(self, *_):
        ids = self.list.selection()
        self.action.state(["!disabled"] if ids else ["disabled"])
        if ids and self.kind.get() != "Recovery":
            self.status.set(self.rows[ids[0]].key)

    def open(self):
        ids = self.list.selection()
        if not ids:
            return
        entry, kind = self.rows[ids[0]], self.kind.get()
        editor = self.editor
        try:
            if kind == "Recovery":
                board = self.library.restore(entry)
                if not editor.discard():
                    return
                editor.load(board, None, recovered=entry)
            else:
                path = Path(entry.key)
                board = load_board(path)
                if kind == "Elements":
                    editor.insert(board.marks)
                elif editor.discard():
                    editor.load(board, path if kind == "Boards" else None)
                else:
                    return
                if kind != "Boards":
                    editor.catalog(lambda: self.library.remember(path, board, kind))
            self.window.destroy()
            editor.studio.show_board()
        except (OSError, ValueError, sqlite3.Error) as err:
            self.status.set(str(err))
