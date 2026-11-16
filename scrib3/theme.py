"""Shared desktop palette and accessible native ttk styles."""
from tkinter import font, ttk

INK = '#172033'
MUTED = '#617085'
BACKGROUND = '#f4f6fa'
SURFACE = '#ffffff'
DESK = '#202937'
PAPER = '#ffffff'
ACCENT = '#2563eb'
TRAVEL = '#d97706'
BORDER = '#dce2eb'


def configure(root):
    families = set(font.families(root))
    family = next((name for name in ('Inter', 'Segoe UI', 'DejaVu Sans') if name in families), 'Arial')
    for name in ('TkDefaultFont', 'TkTextFont'):
        font.nametofont(name).configure(family=family, size=10)
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', background=BACKGROUND, foreground=INK, font=(family, 10))
    style.configure('TButton', padding=(9, 4), background=SURFACE, bordercolor=BORDER,
                    lightcolor=SURFACE, darkcolor=SURFACE, focuscolor=ACCENT)
    style.map('TButton', background=[('disabled', BACKGROUND), ('pressed', '#dbeafe'), ('active', '#eaf1ff')],
              foreground=[('disabled', '#7c8798')], bordercolor=[('focus', ACCENT)])
    style.configure('Primary.TButton', background=ACCENT, foreground='white', bordercolor=ACCENT,
                    lightcolor=ACCENT, darkcolor=ACCENT, font=(family, 10, 'bold'))
    style.map('Primary.TButton', background=[('disabled', '#94a3b8'), ('pressed', '#1e40af'), ('active', '#1d4ed8')],
              foreground=[('disabled', '#f1f5f9'), ('active', 'white')])
    style.configure('Brand.TLabel', font=(family, 24, 'bold'), foreground=INK)
    style.configure('Title.TLabel', font=(family, 12, 'bold'))
    style.configure('Muted.TLabel', foreground=MUTED)
    style.configure('Badge.TLabel', background='#e7edf6', foreground=MUTED, padding=(10, 5), font=(family, 9))
    style.configure('Metric.TFrame', background=SURFACE, relief='solid', borderwidth=1,
                    bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER)
    style.configure('Metric.TLabel', background=SURFACE, foreground=MUTED, font=(family, 9))
    style.configure('MetricValue.TLabel', background=SURFACE, foreground=INK, font=(family, 15, 'bold'))
    style.configure('TNotebook', padding=0, background=BACKGROUND, borderwidth=0)
    style.configure('TNotebook.Tab', padding=(13, 7), background='#e7ecf3', font=(family, 9, 'bold'),
                    bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER)
    style.map('TNotebook.Tab', background=[('selected', SURFACE)], foreground=[('selected', ACCENT)])
    style.configure('TEntry', padding=3, fieldbackground=SURFACE, bordercolor=BORDER,
                    lightcolor=BORDER, darkcolor=BORDER)
    style.map('TEntry', bordercolor=[('focus', ACCENT)])
    style.configure('TCombobox', padding=3, fieldbackground=SURFACE, bordercolor=BORDER)
    style.map('TCombobox', fieldbackground=[('readonly', SURFACE)], foreground=[('readonly', INK)])
    style.configure('TLabelframe', bordercolor=BORDER)
    style.configure('TLabelframe.Label', foreground=MUTED, font=(family, 9, 'bold'))
    style.configure('TSeparator', background=BORDER)
    return family
