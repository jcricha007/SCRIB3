"""Registered GRBL passes advance only after a confirmed completed operation."""

from tkinter import messagebox


class PassWindow:
    def __init__(self, editor):
        self.editor = editor
        self.pens = editor.board.pens()
        self.index = 0
        self.board = editor.board
        self.revision = editor.revision
        self.session = editor.studio.controls.session
        if not self.pens:
            raise ValueError("Add visible pen paths first.")
        self.reference = self.session.snapshot()["reference"] if self.session else None
        self.start(True)

    def start(self, dry):
        editor = self.editor
        if editor.revision != self.revision or editor.board != self.board:
            messagebox.showerror(
                "Pen passes",
                "The board changed. Review its remaining pens again.",
                parent=editor.root,
            )
            return
        if self.index:
            session = editor.studio.controls.session
            if (
                session is not self.session
                or not session
                or session.snapshot()["reference"] != self.reference
            ):
                messagebox.showerror(
                    "Pen passes",
                    "Paper reference changed. Review the remaining colors again.",
                    parent=editor.root,
                )
                return
            if not messagebox.askokcancel(
                "Change pen",
                f"Load {self.pens[self.index]} for pass {self.index+1} of {len(self.pens)}. Keep paper and machine zero in place.",
                parent=editor.root,
            ):
                return
        editor.pen.set(self.pens[self.index])
        editor.sync()
        editor.studio.review(board_editor=editor, on_complete=self.completed, initial_dry=dry)

    def completed(self, job):
        self.index += 1
        if self.index == len(self.pens):
            self.editor.status.set("All color passes completed.")
        else:
            self.start(job.dry_run)
