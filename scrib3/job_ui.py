"""Progress and realtime controls for the single active plotter job."""
import tkinter as tk
from tkinter import ttk


class JobWindow:
    def __init__(self, root, session, operation):
        self.session, self.operation = session, operation
        self.window = tk.Toplevel(root)
        self.window.title('SCRIB3 | Running sketch')
        self.window.geometry('540x260')
        self.window.minsize(500, 250)
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.active = True
        panel = ttk.Frame(self.window, padding=16)
        panel.pack(fill='both', expand=True)
        self.status = tk.StringVar(value='Preparing reviewed sketch…')
        ttk.Label(panel, textvariable=self.status, wraplength=460).pack(anchor='w', pady=8)
        self.progress = ttk.Progressbar(panel, maximum=1)
        self.progress.pack(fill='x', pady=8)
        buttons = ttk.Frame(panel)
        buttons.pack(fill='x', pady=8)
        self.pause = ttk.Button(buttons, text='Pause', command=session.pause_job, state='disabled')
        self.pause.pack(side='left')
        self.resume = ttk.Button(buttons, text='Resume', command=session.resume_job, state='disabled')
        self.resume.pack(side='left', padx=8)
        self.stop = ttk.Button(buttons, text='Stop / reset', command=session.reset)
        self.stop.pack(side='left')
        ttk.Label(panel, text='Pause keeps the pen at its current height. Stop resets the Arduino and requires reconnecting; reset may lower the servo.',
                  style='Muted.TLabel', wraplength=460).pack(anchor='w', pady=8)
        self.after_id = self.window.after(80, self.poll)

    def poll(self):
        snap = self.session.snapshot()
        job, result = snap['job'], snap['last_result']
        state = job['state']
        finished = not snap['connected'] or result and result[0] >= self.operation
        self.active = snap['busy'] and snap['connected'] and not finished
        if result and result[0] == self.operation and result[2]:
            self.status.set(result[2])
        elif state == 'completed':
            self.status.set('Sketch complete. GRBL reports Idle; pen-up command completed.')
        elif state in {'failed', 'stopped'}:
            self.status.set(f"Job {state}: {job['error']} Reconnect and re-establish paper zero before retrying.")
        elif not snap['connected']:
            self.status.set('Disconnected. Reconnect and re-establish paper zero before retrying.')
        else:
            self.status.set(f"{state.capitalize()} • {job['completed']} / {job['total']} lines completed • {snap['state']}")
        self.progress.configure(maximum=max(1, job['total']), value=job['completed'])
        self.pause.state(['!disabled'] if self.active and state == 'running' else ['disabled'])
        self.resume.state(['!disabled'] if self.active and state == 'paused' else ['disabled'])
        self.stop.state(['!disabled'] if self.active else ['disabled'])
        self.after_id = None if finished else self.window.after(80, self.poll)

    def close(self):
        if self.active:
            self.window.iconify()
        else:
            if self.after_id is not None:
                self.window.after_cancel(self.after_id)
            self.window.destroy()
