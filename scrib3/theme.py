"""The SCRIB3 desktop palette, typography and native widget styles."""
from tkinter import font, ttk

INK = '#18283b'
MUTED = '#526477'
BACKGROUND = '#f7f9fc'
SURFACE = '#ffffff'
DESK = '#dce4ed'
PAPER = '#ffffff'
ACCENT = '#2056d8'
TRAVEL = '#b66309'
BORDER = '#cbd5e1'
NAVY = '#142337'
ON_NAVY = '#f4f7ff'
PALE_BLUE = '#90b9ff'
TINT = '#e5edff'
GRID = '#e8edf3'


def configure(root):
    families = set(font.families(root))
    family = next((name for name in ('Inter', 'Avenir Next', 'Segoe UI', 'DejaVu Sans')
                   if name in families), 'Helvetica')
    for name in ('TkDefaultFont', 'TkTextFont', 'TkMenuFont'):
        font.nametofont(name).configure(family=family, size=10)
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', background=BACKGROUND, foreground=INK, font=(family, 10),
                    focuscolor=ACCENT, selectbackground=ACCENT, selectforeground=SURFACE)
    style.configure('TFrame', background=BACKGROUND)
    style.configure('TLabel', background=BACKGROUND)
    style.configure('Title.TLabel', font=(family, 13, 'bold'))
    style.configure('Section.TLabel', foreground=MUTED, font=(family, 10, 'bold'))
    style.configure('Muted.TLabel', foreground=MUTED)
    style.configure('Header.TFrame', background=NAVY)
    style.configure('Brand.TLabel', background=NAVY, foreground=ON_NAVY, font=(family, 21, 'bold'), space=0)
    style.configure('Header.TLabel', background=NAVY, foreground='#c5d4e8', font=(family, 10))
    style.configure('Header.TSeparator', background='#455873')
    style.configure('TSeparator', background=BORDER)
    style.configure('Metric.TFrame', background=SURFACE, relief='solid', borderwidth=1,
                    bordercolor=BORDER, lightcolor=SURFACE, darkcolor=SURFACE)
    style.configure('Metric.TLabel', background=SURFACE, foreground=MUTED, font=(family, 9))
    style.configure('MetricValue.TLabel', background=SURFACE, foreground=INK, font=(family, 15, 'bold'))
    style.configure('Badge.TLabel', background=TINT, foreground='#24478b', padding=(8, 3), font=(family, 9, 'bold'))

    def button(name, background, foreground, border, hover, pressed):
        style.configure(name, background=background, foreground=foreground, bordercolor=border,
                        lightcolor=background, darkcolor=background, relief='flat', borderwidth=1,
                        padding=(9, 4), focuscolor=foreground)
        fills = [('disabled', '#e7ecf2'), ('pressed', pressed), ('active', hover)]
        style.map(name, background=fills, lightcolor=fills, darkcolor=fills,
                  foreground=[('disabled', '#596879')], bordercolor=[('disabled', BORDER), ('focus', ACCENT)])

    button('TButton', SURFACE, INK, BORDER, '#eef3fd', '#dce8ff')
    button('TMenubutton', SURFACE, INK, BORDER, '#eef3fd', '#dce8ff')
    button('Primary.TButton', ACCENT, 'white', ACCENT, '#244fc0', '#1c409f')
    button('Header.TButton', '#22354d', ON_NAVY, '#475a71', '#314963', '#3c536e')
    style.layout('Header.TMenubutton', style.layout('TButton'))
    button('Header.TMenubutton', NAVY, ON_NAVY, NAVY, '#293d57', '#334965')
    style.configure('Header.TMenubutton', padding=(6, 4))
    button('Danger.TButton', '#fff3f1', '#9f302b', '#eac1be', '#fce4e1', '#f5d2cf')

    style.layout('Tool.TRadiobutton', style.layout('TButton'))
    style.configure('Tool.TRadiobutton', anchor='w', padding=(10, 4), borderwidth=1, relief='flat',
                    background=BACKGROUND, bordercolor=BACKGROUND, lightcolor=BACKGROUND, darkcolor=BACKGROUND)
    tool_fills = [('selected', TINT), ('active', '#edf1f7')]
    style.map('Tool.TRadiobutton', background=tool_fills, lightcolor=tool_fills, darkcolor=tool_fills,
              foreground=[('selected', '#163f9c')], bordercolor=[('focus', ACCENT), ('selected', '#9bb9fa')])
    for name in ('TCheckbutton', 'TRadiobutton'):
        style.configure(name, padding=(2, 2), indicatorbackground=SURFACE)
        style.map(name, background=[('active', '#edf2fa')], indicatorbackground=[('selected', TINT)])
    style.configure('TNotebook', padding=0, background=BACKGROUND, borderwidth=0)
    style.configure('TNotebook.Tab', padding=(12, 5), font=(family, 10, 'bold'), background='#e7edf5',
                    foreground=MUTED, borderwidth=1, bordercolor=BORDER, lightcolor='#e7edf5', darkcolor='#e7edf5')
    for option in ('background', 'lightcolor', 'darkcolor'):
        style.map('TNotebook.Tab', **{option: [('selected', ACCENT), ('active', TINT)]})
    style.map('TNotebook.Tab', foreground=[('selected', 'white')], bordercolor=[('selected', ACCENT)])
    for name in ('TEntry', 'TCombobox', 'TSpinbox'):
        style.configure(name, padding=4, fieldbackground=SURFACE, background=SURFACE, foreground=INK,
                        bordercolor=BORDER, lightcolor=SURFACE, darkcolor=SURFACE, arrowcolor=MUTED)
        style.map(name, bordercolor=[('focus', ACCENT)], fieldbackground=[('disabled', '#e7ecf2'), ('readonly', SURFACE)],
                  foreground=[('disabled', MUTED), ('readonly', INK)])
    style.configure('Compact.TEntry', padding=(4, 2))
    style.configure('TLabelframe', relief='solid', borderwidth=1, bordercolor=BORDER)
    style.configure('TLabelframe.Label', foreground=INK, font=(family, 10, 'bold'))
    style.configure('Treeview', background=SURFACE, fieldbackground=SURFACE, foreground=INK,
                    bordercolor=BORDER, rowheight=root.winfo_pixels('15p'), indent=0)
    style.map('Treeview', background=[('selected', TINT)], foreground=[('selected', INK)])
    style.configure('Treeview.Heading', background=BACKGROUND, foreground=MUTED, font=(family, 9, 'bold'),
                    borderwidth=0, padding=(4, 2))
    style.configure('Horizontal.TProgressbar', background=ACCENT, troughcolor='#e1e8f2', borderwidth=0)
    for name in ('Vertical.TScrollbar', 'Horizontal.TScrollbar'):
        style.configure(name, background=BORDER, troughcolor=BACKGROUND, arrowcolor=MUTED, borderwidth=0)
    for widget in ('Listbox', 'Text', 'Menu'):
        for option, value in (('background', SURFACE), ('foreground', INK), ('relief', 'flat'),
                              ('borderWidth', 0), ('selectBackground', ACCENT), ('selectForeground', SURFACE)):
            root.option_add(f'*{widget}.{option}', value)
    root.option_add('*Menu.activeBackground', TINT)
    root.option_add('*Menu.activeForeground', INK)
    root.option_add('*Text.insertBackground', INK)
    root.option_add('*Listbox.highlightColor', ACCENT)
    root.option_add('*Listbox.highlightBackground', BORDER)
    root.option_add('*Toplevel.background', BACKGROUND)
    return family
