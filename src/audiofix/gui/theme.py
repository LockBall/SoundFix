from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk


@dataclass(frozen=True)
class Theme:
    name: str
    background: str
    foreground: str
    muted_foreground: str
    field_background: str
    field_foreground: str
    selection_foreground: str
    accent: str
    border: str


THEMES = {
    "dark": Theme(
        name="dark",
        background="#1f2328",
        foreground="#f0f3f6",
        muted_foreground="#a8b0ba",
        field_background="#2d333b",
        field_foreground="#f0f3f6",
        selection_foreground="#ffffff",
        accent="#4f8cff",
        border="#444c56",
    ),
    "light": Theme(
        name="light",
        background="#f7f7f7",
        foreground="#202428",
        muted_foreground="#5f6872",
        field_background="#ffffff",
        field_foreground="#202428",
        selection_foreground="#ffffff",
        accent="#1f6feb",
        border="#c8d0d8",
    ),
}

DEFAULT_THEME = "dark"


def apply_theme(root: tk.Tk, theme_name: str) -> Theme:
    theme = THEMES[theme_name]
    style = ttk.Style(root)
    style.theme_use("clam")

    root.configure(background=theme.background)

    style.configure(".", background=theme.background, foreground=theme.foreground)
    style.configure("TFrame", background=theme.background)
    style.configure("TLabel", background=theme.background, foreground=theme.foreground)
    style.configure(
        "Muted.TLabel",
        background=theme.background,
        foreground=theme.muted_foreground,
    )
    style.configure(
        "SelectedScale.TLabel",
        background=theme.accent,
        foreground=theme.selection_foreground,
    )
    style.configure(
        "Status.TLabel",
        background=theme.field_background,
        foreground=theme.foreground,
        bordercolor=theme.border,
        relief="solid",
        borderwidth=1,
        padding=(8, 4),
    )
    style.configure(
        "TButton",
        background=theme.field_background,
        foreground=theme.foreground,
        bordercolor=theme.border,
        focusthickness=1,
        focuscolor=theme.accent,
        padding=(10, 6),
    )
    style.map(
        "TButton",
        background=[("active", theme.border), ("pressed", theme.border)],
        foreground=[("disabled", theme.muted_foreground)],
    )
    style.configure(
        "TCheckbutton",
        background=theme.background,
        foreground=theme.foreground,
        focuscolor=theme.accent,
    )
    style.map(
        "TCheckbutton",
        background=[("active", theme.background)],
        foreground=[("disabled", theme.muted_foreground)],
    )
    style.configure(
        "TEntry",
        fieldbackground=theme.field_background,
        background=theme.field_background,
        foreground=theme.field_foreground,
        insertcolor=theme.field_foreground,
        bordercolor=theme.border,
        lightcolor=theme.border,
        darkcolor=theme.border,
        padding=(6, 4),
    )
    style.map(
        "TEntry",
        fieldbackground=[
            ("disabled", theme.background),
            ("readonly", theme.field_background),
            ("!disabled", theme.field_background),
        ],
        foreground=[
            ("disabled", theme.muted_foreground),
            ("readonly", theme.field_foreground),
            ("!disabled", theme.field_foreground),
        ],
        selectbackground=[("!disabled", theme.accent)],
        selectforeground=[("!disabled", theme.selection_foreground)],
    )
    style.configure(
        "TCombobox",
        fieldbackground=theme.field_background,
        background=theme.field_background,
        foreground=theme.field_foreground,
        bordercolor=theme.border,
        arrowcolor=theme.foreground,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", theme.field_background)],
        foreground=[("readonly", theme.field_foreground)],
        selectbackground=[("readonly", theme.field_background)],
        selectforeground=[("readonly", theme.field_foreground)],
    )
    return theme
