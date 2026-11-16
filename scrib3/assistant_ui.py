"""Local Ollama conversation and reviewed geometry proposals. No controller access."""
from queue import Empty, SimpleQueue
from threading import Event, Thread
import tkinter as tk
from tkinter import ttk

from . import ollama
from .drawing import Sheet, fit_to_sheet


class AssistantWindow:
    def __init__(self, studio):
        self.studio = studio
        self.window = tk.Toplevel(studio.root)
        self.window.title('SCRIB3 | Local design assistant')
        self.window.geometry('940x720')
        self.window.minsize(720, 600)
        self.window.protocol('WM_DELETE_WINDOW', self.hide)
        self.events = SimpleQueue()
        self.cancel = Event()
        self.busy = False
        self.closed = False
        self.history = []
        self.draft = None
        self.draft_name = ''
        self.task_buttons = []
        self.status = tk.StringVar(value='Looking for local Ollama…')
        panel = ttk.Frame(self.window, padding=16)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='Local design assistant', style='Title.TLabel').pack(anchor='w')
        bar = ttk.Frame(panel)
        bar.pack(fill='x', pady=8)
        ttk.Label(bar, text='Model').pack(side='left', padx=(0, 8))
        self.models = ttk.Combobox(bar, textvariable=studio.model, state='readonly', width=30)
        self.models.pack(side='left', fill='x', expand=True)
        self.models.bind('<<ComboboxSelected>>', lambda _: self.clear_chat())
        self.button(bar, 'Refresh models', self.refresh_models).pack(side='left', padx=6)
        ttk.Button(bar, text='Save choice', command=studio.save_preset).pack(side='left')
        ttk.Label(panel, text='Ollama on this Mac/PC • Chat and artwork proposals • Apply drawings in the preview',
                  style='Muted.TLabel', wraplength=660).pack(anchor='w')
        footer = ttk.Frame(panel)
        footer.pack(side='bottom', fill='x', pady=(8, 0))
        self.stop_button = ttk.Button(footer, text='Cancel request', command=self.cancel_request, state='disabled')
        self.stop_button.pack(side='right')
        ttk.Label(footer, textvariable=self.status, wraplength=520, style='Muted.TLabel').pack(side='left', fill='x')
        self.tabs = ttk.Notebook(panel)
        self.tabs.pack(fill='both', expand=True, pady=(10, 0))
        chat = ttk.Frame(self.tabs, padding=10)
        create = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(chat, text='Chat')
        self.tabs.add(create, text='Create / revise')
        self.chat_output = self.text_area(chat, 8, readonly=True, expand=True)
        ttk.Label(chat, text='Recent conversation and a summary of the design are included.').pack(anchor='w', pady=5)
        self.chat_input = self.text_area(chat, 4)
        actions = ttk.Frame(chat)
        actions.pack(fill='x', pady=(8, 0))
        self.button(actions, 'Send', self.send_chat).pack(side='left')
        self.button(actions, 'Use prompt as design brief', self.prompt_to_design).pack(side='left', padx=6)
        self.button(actions, 'New conversation', self.clear_chat).pack(side='right')
        create_footer = ttk.Frame(create)
        create_footer.pack(side='bottom', fill='x')
        self.draft_status = tk.StringVar(value='Your generated drawing will appear here before you apply it.')
        ttk.Label(create_footer, textvariable=self.draft_status, wraplength=640).pack(anchor='w', pady=6)
        self.apply_button = ttk.Button(create_footer, text='Use drawing in workspace', command=self.apply, state='disabled')
        self.apply_button.pack(anchor='e')
        ttk.Label(create, text='Describe the line drawing or the changes you want.').pack(anchor='w')
        self.design_input = self.text_area(create, 4)
        self.design_input.insert('1.0', 'Draw a mountain valley with a winding river and three pine trees.')
        actions = ttk.Frame(create)
        actions.pack(fill='x', pady=8)
        self.button(actions, 'Create new drawing', lambda: self.generate(False)).pack(side='left')
        self.button(actions, 'Revise workspace drawing', lambda: self.generate(True)).pack(side='left', padx=6)
        self.preview = tk.Canvas(create, background='#e4e9e1', highlightthickness=0, height=100)
        self.preview.pack(fill='both', expand=True)
        self.preview.bind('<Configure>', lambda _: self.paint())
        self.after_id = self.window.after(80, self.poll)
        self.window.after(100, self.refresh_models)

    def text_area(self, parent, height, readonly=False, expand=False):
        frame = ttk.Frame(parent)
        frame.pack(fill='both' if expand else 'x', expand=expand)
        text = tk.Text(frame, height=height, width=40, wrap='word', background='#fffef8', padx=8, pady=6)
        scroll = ttk.Scrollbar(frame, command=text.yview)
        scroll.pack(side='right', fill='y')
        text.configure(yscrollcommand=scroll.set)
        text.pack(fill='both', expand=True)
        if readonly:
            text.configure(state='disabled')
        return text

    def button(self, parent, text, command):
        button = ttk.Button(parent, text=text, command=command)
        self.task_buttons.append(button)
        return button

    def append(self, text):
        self.chat_output.configure(state='normal')
        self.chat_output.insert('end', text)
        self.chat_output.see('end')
        self.chat_output.configure(state='disabled')

    def start(self, action, complete, title, chat=False):
        if self.busy or self.closed:
            return
        self.busy = True
        self.cancel = Event()
        cancel = self.cancel
        self.status.set(title)
        self.models.configure(state='disabled')
        for button in self.task_buttons:
            button.state(['disabled'])
        self.stop_button.state(['!disabled'])
        def work():
            try:
                result = action(cancel)
            except Exception as exc:
                # Keep unexpected model/transport failures inside the window.
                self.events.put(('done', (complete, None, str(exc), chat)))
            else:
                self.events.put(('done', (complete, result, None, chat)))
        Thread(target=work, daemon=True, name='SCRIB3 Ollama').start()

    def poll(self):
        if self.closed:
            return
        for _ in range(500):
            try:
                kind, value = self.events.get_nowait()
            except Empty:
                break
            if kind == 'chunk':
                if not self.cancel.is_set():
                    self.append(value)
                continue
            complete, result, error, chat = value
            self.busy = False
            self.models.configure(state='readonly')
            for button in self.task_buttons:
                button.state(['!disabled'])
            self.stop_button.state(['disabled'])
            if self.cancel.is_set():
                self.status.set('Request cancelled. Its result was discarded.')
                if chat:
                    self.append('\n[Cancelled; not added to conversation context.]\n\n')
            elif error:
                self.status.set(error)
                if chat:
                    self.append('\n[Response failed: ' + error + ']\n\n')
            else:
                complete(result)
        self.after_id = self.window.after(80, self.poll)

    def refresh_models(self):
        def show(names):
            self.models.configure(values=names)
            if self.studio.model.get() not in names:
                self.studio.model.set(names[0] if names else '')
            self.status.set(f'Connected to local Ollama • {len(names)} local models.' if names else
                            'Ollama is running, but no local models are installed. Install a model, then refresh.')
        self.start(lambda _: ollama.local_models(), show, 'Checking Ollama and installed models…')

    def context(self):
        app = self.studio
        return (f'Design name: {app.source_name.get()}\nPaper: {app.sheet.width:g} × {app.sheet.height:g} mm; '
                f'margin {app.sheet.margin:g} mm; {len(app.source)} source strokes. '
                f'UI units: {app.unit}. Pen up: {app.pen_up.get()}; pen down: {app.pen_down.get()}. '
                'Drawing is not yet physically validated. No live controller state is supplied.')

    def send_chat(self):
        prompt = self.chat_input.get('1.0', 'end-1c').strip()
        if self.busy or not prompt:
            return
        if len(prompt) > 8000:
            self.status.set('Keep each chat message under 8,000 characters.')
            return
        model, context = self.studio.model.get(), self.context()
        messages = [*self.history, {'role': 'user', 'content': prompt}]
        self.append('You\n' + prompt + '\n\nOllama\n')
        def complete(reply):
            self.history = [*messages, {'role': 'assistant', 'content': reply}][-12:]
            self.append('\n\n')
            self.status.set('Reply complete. Use Create / revise to turn a brief into line art.')
        self.start(lambda cancel: ollama.chat(model, messages, context, cancel=cancel,
                   on_chunk=lambda part: self.events.put(('chunk', part))), complete, 'Waiting for local model…', chat=True)

    def prompt_to_design(self):
        prompt = self.chat_input.get('1.0', 'end-1c').strip()
        if prompt:
            self.design_input.delete('1.0', 'end')
            self.design_input.insert('1.0', prompt)
        self.tabs.select(1)

    def clear_chat(self):
        if self.busy:
            return
        self.history.clear()
        self.chat_output.configure(state='normal')
        self.chat_output.delete('1.0', 'end')
        self.chat_output.configure(state='disabled')
        self.status.set('New conversation. The workspace drawing is unchanged.')

    def generate(self, revise=False):
        if self.busy:
            return
        prompt = self.design_input.get('1.0', 'end-1c').strip()
        model = self.studio.model.get()
        reference = self.studio.source if revise else None
        name = ('AI revision: ' if revise else 'AI: ') + prompt[:65]
        def show(drawing):
            self.draft, self.draft_name = drawing, name
            self.apply_button.state(['!disabled'])
            self.draft_status.set(f'{len(drawing)} strokes • Preview only. Use drawing replaces the workspace; Undo restores it.')
            self.paint()
            self.status.set('Drawing ready to review.')
        self.start(lambda _: ollama.generate_drawing(model, prompt, reference), show, 'Generating line art in Ollama…')

    def paint(self):
        self.preview.delete('all')
        if not self.draft:
            self.preview.create_text(20, 20, anchor='nw', text='Drawing preview', fill='#555e54')
            return
        width, height = max(60, self.preview.winfo_width()), max(60, self.preview.winfo_height())
        for stroke in fit_to_sheet(self.draft, Sheet(width, height, 16)):
            self.preview.create_line(*(value for x, y in stroke for value in (x, height-y)), fill='#262a25', width=1.2)

    def apply(self):
        if self.draft is None:
            return
        try:
            self.studio.set_drawing(self.draft_name, self.draft)
        except ValueError as exc:
            self.status.set(str(exc))
            return
        self.studio.status.set('AI drawing applied. Review its paths before exporting.')
        self.status.set('Applied to workspace. Undo design restores the previous drawing.')

    def cancel_request(self):
        if self.busy:
            self.cancel.set()
            self.status.set('Cancelling: results will be discarded. Waiting for the local request to return.')
            self.stop_button.state(['disabled'])

    def hide(self):
        self.cancel_request()
        self.window.withdraw()

    def shutdown(self):
        self.closed = True
        self.cancel.set()
        self.window.after_cancel(self.after_id)
        self.window.destroy()
