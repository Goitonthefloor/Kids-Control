"""Settings window for how the child PC shows warnings."""

from __future__ import annotations

from kidscontrol_agent.enforce import notify
from kidscontrol_agent.notify_style import load_notify_style, save_notify_style


def _text_settings() -> int:
    current = load_notify_style()
    print("KidsControl Einstellungen")
    print("Wie sollen Warnungen erscheinen?")
    print(f"  1  Meldungsfenster{'  (aktiv)' if current == 'window' else ''}")
    print(f"  2  Toast{'  (aktiv)' if current == 'toast' else ''}")
    choice = input("Auswahl [1/2]: ").strip()
    style = "window" if choice == "1" else "toast" if choice == "2" else ""
    if not style:
        print("Unverändert.")
        return 0
    try:
        path = save_notify_style(style)
    except OSError as exc:
        print(exc)
        return 1
    print(f"Gespeichert: {'Meldungsfenster' if style == 'window' else 'Toast'} ({path})")
    return 0


def _build_settings_window():
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("KidsControl Einstellungen")
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=16)
    frame.grid(row=0, column=0)
    ttk.Label(frame, text="Warnungen", font=("", 14, "bold")).grid(row=0, column=0, sticky="w")
    ttk.Label(
        frame,
        text="Wie sollen Warnungen auf diesem PC erscheinen?",
    ).grid(row=1, column=0, sticky="w", pady=(8, 8))
    style = tk.StringVar(value=load_notify_style())
    ttk.Radiobutton(
        frame,
        text="Meldungsfenster  –  muss bestätigt werden",
        variable=style,
        value="window",
    ).grid(row=2, column=0, sticky="w")
    ttk.Radiobutton(
        frame,
        text="Toast  –  kurzer Hinweis, verschwindet von selbst",
        variable=style,
        value="toast",
    ).grid(row=3, column=0, sticky="w", pady=(4, 8))
    status = ttk.Label(frame, text="")
    status.grid(row=5, column=0, sticky="w", pady=(8, 0))

    def remember() -> bool:
        try:
            path = save_notify_style(style.get())
        except OSError as exc:
            status.config(text=str(exc))
            print(exc)
            return False
        label = "Meldungsfenster" if style.get() == "window" else "Toast"
        status.config(text=f"Gespeichert: {label}")
        print(f"Gespeichert: {label} ({path})")
        return True

    def preview() -> None:
        remember()
        notify("KidsControl", "So sieht eine Warnung aus.", style=style.get())

    buttons = ttk.Frame(frame)
    buttons.grid(row=4, column=0, sticky="w")
    ttk.Button(buttons, text="Speichern", command=remember).grid(row=0, column=0, padx=(0, 8))
    ttk.Button(buttons, text="Ausprobieren", command=preview).grid(row=0, column=1)
    return root


def _gui_settings() -> int:
    root = _build_settings_window()
    root.mainloop()
    return 0


def open_settings() -> int:
    try:
        return _gui_settings()
    except Exception as exc:
        print(f"Fenster nicht verfügbar ({exc}).")
        return _text_settings()
