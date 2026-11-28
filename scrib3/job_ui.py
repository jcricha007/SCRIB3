"""Progress and realtime controls for the single active plotter job."""
import tkinter as tk
from tkinter import ttk


class JobWindow:
    def __init__(self, root, session, operation, on_complete=None, *, timeline=None):
        self.on_complete = on_complete
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
        self.trace = None
        if timeline is not None:
            from .timeline_ui import TraceView
            self.window.geometry('640x490')
            self.trace = TraceView(panel, timeline)
            self.trace.pack(fill='both', expand=True)
        self.progress = ttk.Progressbar(panel, maximum=1)
        self.progress.pack(fill='x', pady=8)
        buttons = ttk.Frame(panel)
        buttons.pack(fill='x', pady=8)
        self.pause = ttk.Button(buttons, text='Pause', command=lambda: session.pause_job(operation), state='disabled')
        self.pause.pack(side='left')
        self.resume = ttk.Button(buttons, text='Resume', command=lambda: session.resume_job(operation), state='disabled')
        self.resume.pack(side='left', padx=8)
        self.stop = ttk.Button(buttons, text='Stop print', style='Danger.TButton', command=lambda: session.stop_job(operation))
        self.stop.pack(side='left')
        ttk.Label(panel, text='Stop finishes buffered moves and raises the pen. From Pause, buffered moves resume to finish. Connection and home stay set. Use Control reset for an immediate abort.',
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
            self.status.set('Sketch complete. The pen-up command finished at the last drawing point. GRBL is idle.')
        elif state == 'stopped' and snap['connected']:
            self.status.set('Print stopped with pen raised. Connection and paper zero retained.')
        elif state in {'failed', 'stopped'}:
            self.status.set(f"Job {state}: {job['error']} Reconnect and re-establish paper zero before retrying.")
        elif not snap['connected']:
            self.status.set('Disconnected. Reconnect and re-establish paper zero before retrying.')
        else:
            self.status.set(f"{state.capitalize()} • {job['accepted']} / {job['total']} lines accepted • {snap['state']}\n"
                            f"Motion confirmed through line {job['completed']}; accepted lines may still be queued.")
        stopped = state == 'stopped' and snap['connected'] and not job['error']
        if (self.trace is not None and job.get('operation') == self.operation
                and job['total'] == len(self.trace.timeline.events)
                and (job['completed'] != self.trace.count or self.trace.stopped != stopped)):
            self.trace.show(job['completed'], stopped=stopped)
        self.progress.configure(maximum=max(1, job['total']), value=job['accepted'])
        self.pause.state(['!disabled'] if self.active and state == 'running' else ['disabled'])
        self.resume.state(['!disabled'] if self.active and state == 'paused' else ['disabled'])
        self.stop.state(['!disabled'] if self.active and state != 'stopping' else ['disabled'])
        self.after_id = None if finished else self.window.after(80, self.poll)
        if finished and snap['connected'] and state == 'completed' and result and result[0] == self.operation and not result[2] and self.on_complete:
            callback, self.on_complete = self.on_complete, None
            self.window.after_idle(callback)

    def close(self):
        if self.active:
            self.window.iconify()
        else:
            if self.after_id is not None:
                self.window.after_cancel(self.after_id)
            self.window.destroy()
