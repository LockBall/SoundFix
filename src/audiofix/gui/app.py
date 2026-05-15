"""Tkinter GUI entry point.

The GUI is intentionally thin. Conversion planning and ffmpeg execution belong
in audiofix.core so the same behavior can later be reused by tests or a CLI.
"""

import os
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, filedialog
from tkinter import ttk

from audiofix import __version__
from audiofix.core.config import (
    CONTROL_TITLE_GAP_PX,
    DB_DISPLAY_DECIMALS,
    DEFAULT_DB_INTERVAL,
    DEFAULT_ENCODER_MODE,
    DEFAULT_INITIAL_GAIN_DB_TEXT,
    DEFAULT_MAX_DB,
    DEFAULT_MIN_DB,
    DEFAULT_PEAK_MARGIN_DB,
    DEFAULT_PEAK_REFINEMENT_SCALE,
    DEFAULT_VORBIS_QUALITY,
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    ENCODER_MODE_BITRATE,
    ENCODER_MODE_QUALITY,
    VORBIS_QUALITY_BITRATES,
    get_runtime_paths,
)
from audiofix.core.ffmpeg import (
    FfmpegOptions,
    AudioInfo,
    build_ffmpeg_command,
    check_ffmpeg_tools,
    convert_plan_item,
    gain_to_peak_margin_db,
    measure_max_volume_db,
    probe_audio_info,
    refine_gain_for_encoded_peak_with_history,
    scale_gain_db,
)
from audiofix.core.planning import (
    build_output_plan,
    calculate_step_count,
)
from audiofix.gui.theme import DEFAULT_THEME, THEMES, apply_theme

VORBIS_QUALITY_VALUES = [value / 2 for value in range(-2, 21)]
ENCODER_MODE_LABELS = {
    "Vorbis Quality": ENCODER_MODE_QUALITY,
    "Match Source Bitrate": ENCODER_MODE_BITRATE,
}
ENCODER_MODE_NAMES = {value: label for label, value in ENCODER_MODE_LABELS.items()}


def build_menu(root: tk.Tk, theme_var: tk.StringVar) -> tk.Menu:
    menu_bar = tk.Menu(root)

    view_menu = tk.Menu(menu_bar, tearoff=False)
    theme_menu = tk.Menu(view_menu, tearoff=False)
    for theme_name in THEMES:
        theme_menu.add_radiobutton(
            label=theme_name.title(),
            variable=theme_var,
            value=theme_name,
        )
    view_menu.add_cascade(label="Theme", menu=theme_menu)
    menu_bar.add_cascade(label="View", menu=view_menu)

    help_menu = tk.Menu(menu_bar, tearoff=False)
    help_menu.add_command(
        label="About AudioFix",
        command=lambda: messagebox.showinfo(
            title="About AudioFix",
            message=(
                f"AudioFix {__version__}\n\n"
                "Batch loudness converter for generating quieter game audio variants."
            ),
        ),
    )
    menu_bar.add_cascade(label="Help", menu=help_menu)

    return menu_bar


def main() -> None:
    root = tk.Tk()
    root.title("AudioFix")
    root.geometry(f"{DEFAULT_WINDOW_WIDTH}x{DEFAULT_WINDOW_HEIGHT}")
    root.minsize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
    apply_theme(root, DEFAULT_THEME)

    frame = ttk.Frame(root, padding=16)
    frame.grid(row=0, column=0, sticky="nsew")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(2, weight=1)

    theme_var = tk.StringVar(value=DEFAULT_THEME)
    root.configure(menu=build_menu(root, theme_var))

    def on_theme_changed(*_: object) -> None:
        apply_theme(root, theme_var.get())

    def clear_entry_focus(event: tk.Event) -> None:
        widget = event.widget
        if isinstance(widget, (tk.Entry, ttk.Entry, tk.Text)):
            return
        root.focus_set()

    theme_var.trace_add("write", on_theme_changed)
    root.bind("<Button-1>", clear_entry_focus, add="+")

    runtime_paths = get_runtime_paths()
    media_dir = runtime_paths.project_root / "media"

    file_path_var = tk.StringVar(value="")
    max_db_var = tk.StringVar(value="")
    min_db_var = tk.StringVar(value="")
    initial_gain_db_var = tk.StringVar(value=DEFAULT_INITIAL_GAIN_DB_TEXT)
    db_interval_var = tk.StringVar(value="")
    peak_margin_db_var = tk.StringVar(value="")
    peak_refinement_scale_var = tk.StringVar(value="")
    step_count_var = tk.StringVar(value="")
    output_folder_var = tk.StringVar(value="")
    audio_info_var = tk.StringVar(value="Audio info: select an input file.")
    overwrite_var = tk.BooleanVar(value=False)
    encoder_mode_choice_var = tk.StringVar(value=ENCODER_MODE_NAMES[DEFAULT_ENCODER_MODE])
    vorbis_quality_var = tk.DoubleVar(value=DEFAULT_VORBIS_QUALITY)
    vorbis_quality_labels: list[ttk.Label] = []
    status_var = tk.StringVar(value="Ready.")
    ffmpeg_status_var = tk.StringVar(value="")
    ffprobe_status_var = tk.StringVar(value="")
    command_preview_var = tk.StringVar(value="ffmpeg command preview unavailable.")
    peak_analysis_results_var = tk.StringVar(value="1 --")
    last_audio_info: list[AudioInfo | None] = [None]
    last_output_folder: list[Path | None] = [None]
    last_refined_gain_db: list[float | None] = [None]

    def format_db(value: float, signed: bool = False) -> str:
        sign = "+" if signed else ""
        return f"{value:{sign}.{DB_DISPLAY_DECIMALS}f}"

    max_db_var.set(format_db(DEFAULT_MAX_DB))
    min_db_var.set(format_db(DEFAULT_MIN_DB))
    db_interval_var.set(format_db(DEFAULT_DB_INTERVAL))
    peak_margin_db_var.set(format_db(DEFAULT_PEAK_MARGIN_DB))
    peak_refinement_scale_var.set(format_db(DEFAULT_PEAK_REFINEMENT_SCALE))

    def refresh_tool_status() -> None:
        tool_status = check_ffmpeg_tools()
        ffmpeg_status_var.set(tool_status.ffmpeg.display_text())
        ffprobe_status_var.set(tool_status.ffprobe.display_text())

    def format_audio_info(info: AudioInfo) -> str:
        bit_rate = f"{round(info.bit_rate / 1000)} kbps" if info.bit_rate else "unknown bitrate"
        sample_rate = f"{info.sample_rate} Hz" if info.sample_rate else "unknown sample rate"
        channels = f"{info.channels} ch" if info.channels else "unknown channels"
        return f"Audio info: {info.codec_name}, {bit_rate}, {sample_rate}, {channels}"

    def get_audio_info(source_path: Path) -> AudioInfo | None:
        tool_status = check_ffmpeg_tools()
        ffmpeg_status_var.set(tool_status.ffmpeg.display_text())
        ffprobe_status_var.set(tool_status.ffprobe.display_text())
        if not tool_status.ffprobe.available or tool_status.ffprobe.path is None:
            error = tool_status.ffprobe.error or "ffprobe not found"
            audio_info_var.set(f"Audio info: {error}.")
            return None
        try:
            info = probe_audio_info(tool_status.ffprobe.path, source_path)
        except (RuntimeError, ValueError) as error:
            audio_info_var.set(f"Audio info: {error}")
            last_audio_info[0] = None
            return None
        audio_info_var.set(format_audio_info(info))
        last_audio_info[0] = info
        return info

    def update_step_count(*_: object) -> None:
        try:
            step_count = calculate_step_count(
                min_db=float(min_db_var.get()),
                db_interval=float(db_interval_var.get()),
            )
        except ValueError:
            step_count_var.set("Invalid")
            return
        step_count_var.set(str(step_count))

    def format_quality_value(quality: float) -> str:
        return f"{quality:g}"

    def format_quality_bitrate(quality: float) -> str:
        if quality.is_integer():
            return VORBIS_QUALITY_BITRATES[int(quality)].split()[0]
        return ""

    def update_vorbis_quality_markers(*_: object) -> None:
        selected_quality = round(vorbis_quality_var.get() * 2) / 2
        if selected_quality != vorbis_quality_var.get():
            vorbis_quality_var.set(selected_quality)
            return
        for label, quality in zip(vorbis_quality_labels, VORBIS_QUALITY_VALUES):
            label.configure(
                style="SelectedScale.TLabel"
                if quality == selected_quality
                else "Muted.TLabel"
            )

    def get_ffmpeg_options(audio_info: AudioInfo | None, overwrite: bool) -> FfmpegOptions:
        encoder_mode = ENCODER_MODE_LABELS[encoder_mode_choice_var.get()]
        audio_bitrate = (
            f"{audio_info.bit_rate}"
            if encoder_mode == ENCODER_MODE_BITRATE and audio_info and audio_info.bit_rate
            else None
        )
        vorbis_quality = float(vorbis_quality_var.get()) if encoder_mode == ENCODER_MODE_QUALITY else None
        return FfmpegOptions(
            audio_bitrate=audio_bitrate,
            sample_rate=audio_info.sample_rate if audio_info else None,
            channels=audio_info.channels if audio_info else None,
            encoder_mode=encoder_mode,
            vorbis_quality=vorbis_quality,
            overwrite=overwrite,
        )

    def update_command_preview(*_: object) -> None:
        source_text = file_path_var.get().strip()
        output_text = output_folder_var.get().strip()
        if not source_text or not output_text:
            command_preview_var.set("ffmpeg command preview unavailable.")
            return

        tool_status = check_ffmpeg_tools()
        if not tool_status.ffmpeg.available or tool_status.ffmpeg.path is None:
            command_preview_var.set("ffmpeg command preview unavailable: ffmpeg missing.")
            return

        try:
            initial_gain_db = float(initial_gain_db_var.get())
        except ValueError:
            command_preview_var.set("ffmpeg command preview unavailable: enter Initial dB.")
            return

        try:
            db_interval = float(db_interval_var.get())
        except ValueError:
            command_preview_var.set("ffmpeg command preview unavailable: enter dB interval.")
            return

        source_path = Path(source_text)
        output_dir = Path(output_text)
        plan = build_output_plan(
            source_path=source_path,
            output_dir=output_dir,
            db_offset=initial_gain_db,
            step_count=1,
            db_interval=-abs(db_interval),
        )
        command = build_ffmpeg_command(
            ffmpeg_path=tool_status.ffmpeg.path,
            source_path=source_path,
            item=plan[0],
            options=get_ffmpeg_options(last_audio_info[0], overwrite_var.get()),
        )
        display_command = ["ffmpeg", *command[1:]]
        command_preview_var.set(
            " ".join(f'"{part}"' if " " in part else part for part in display_command)
        )

    def format_decimal_var(value_var: tk.StringVar) -> None:
        try:
            value_var.set(format_db(float(value_var.get())))
        except ValueError:
            return

    def on_peak_margin_focus_out() -> None:
        if not peak_margin_db_var.get().strip():
            peak_margin_db_var.set(format_db(0.0))
        format_decimal_var(peak_margin_db_var)
        last_refined_gain_db[0] = None
        peak_analysis_results_var.set("1 --")
        status_var.set("Peak margin changed. Click Analyze peak to recalculate Initial dB.")

    def apply_refined_gain_scale() -> None:
        if last_refined_gain_db[0] is None:
            return
        try:
            scale = float(peak_refinement_scale_var.get())
        except ValueError:
            status_var.set("Enter a valid peak scale value.")
            return
        initial_gain_db_var.set(format_db(scale_gain_db(last_refined_gain_db[0], scale)))
        update_command_preview()

    def on_peak_scale_focus_out() -> None:
        if not peak_refinement_scale_var.get().strip():
            peak_refinement_scale_var.set(format_db(1.0))
        format_decimal_var(peak_refinement_scale_var)
        apply_refined_gain_scale()

    def browse_file() -> None:
        path = filedialog.askopenfilename(
            title="Select input audio file",
            initialdir=str(media_dir),
            filetypes=(
                ("Audio files", "*.wav *.mp3 *.flac *.ogg *.m4a"),
                ("All files", "*.*"),
            ),
        )
        if path:
            input_path = Path(path)
            file_path_var.set(str(input_path))
            output_folder_var.set(str(input_path.with_name(f"{input_path.stem}_out")))
            last_audio_info[0] = None
            last_refined_gain_db[0] = None
            peak_analysis_results_var.set("1 --")
            last_output_folder[0] = None
            open_output_button.state(["disabled"])
            get_audio_info(input_path)
            update_command_preview()

    def browse_output_folder() -> None:
        path = filedialog.askdirectory(
            title="Select output folder",
            initialdir=str(media_dir),
        )
        if path:
            output_folder_var.set(str(Path(path)))
            last_output_folder[0] = None
            open_output_button.state(["disabled"])
            update_command_preview()

    def analyze_peak() -> None:
        source_text = file_path_var.get().strip()
        if not source_text:
            status_var.set("Select an input file before analyzing peak.")
            return

        source_path = Path(source_text)
        if not source_path.is_file():
            status_var.set("Select a valid input file before analyzing peak.")
            return

        tool_status = check_ffmpeg_tools()
        ffmpeg_status_var.set(tool_status.ffmpeg.display_text())
        ffprobe_status_var.set(tool_status.ffprobe.display_text())
        if not tool_status.ffmpeg.available or tool_status.ffmpeg.path is None:
            status_var.set("ffmpeg unavailable; cannot analyze peak.")
            return

        audio_info = get_audio_info(source_path)
        if audio_info is None:
            status_var.set("Cannot read input audio settings before peak analysis.")
            return
        if ENCODER_MODE_LABELS[encoder_mode_choice_var.get()] == ENCODER_MODE_BITRATE and audio_info.bit_rate is None:
            status_var.set("Input audio bitrate is unknown; cannot refine peak analysis.")
            return

        status_var.set("Analyzing peak...")
        root.update_idletasks()
        try:
            max_volume_db = measure_max_volume_db(tool_status.ffmpeg.path, source_path)
            peak_margin_db = float(peak_margin_db_var.get())
        except ValueError:
            status_var.set("Enter a valid peak margin dB value.")
            return
        except RuntimeError as error:
            status_var.set(f"Peak analysis failed: {error}")
            return

        initial_gain_db = gain_to_peak_margin_db(max_volume_db, peak_margin_db)
        peak_analysis_results_var.set(f"1)    {format_db(initial_gain_db, signed=True)}")
        peak_target_db = -abs(peak_margin_db)
        status_var.set("Refining peak through Ogg encode...")
        root.update_idletasks()
        options = get_ffmpeg_options(audio_info, True)
        try:
            refined_gain_db, encoded_peak_db, refinement_history = refine_gain_for_encoded_peak_with_history(
                ffmpeg_path=tool_status.ffmpeg.path,
                source_path=source_path,
                initial_gain_db=initial_gain_db,
                peak_target_db=peak_target_db,
                options=options,
            )
        except RuntimeError as error:
            status_var.set(f"Peak refinement failed: {error}")
            return

        final_error_db = encoded_peak_db - peak_target_db
        recommended_gain_db = refined_gain_db - final_error_db
        last_refined_gain_db[0] = recommended_gain_db
        peak_analysis_results_var.set(
            "\n".join(
                [
                    f"1)    {format_db(initial_gain_db, signed=True)}",
                    *[
                        f"{result.pass_number + 1})    {format_db(result.encoded_peak_db, signed=True)}"
                        for result in refinement_history
                    ],
                ]
            )
        )
        try:
            peak_scale = float(peak_refinement_scale_var.get())
        except ValueError:
            status_var.set("Enter a valid peak scale value.")
            return
        scaled_gain_db = scale_gain_db(recommended_gain_db, peak_scale)
        initial_gain_db_var.set(format_db(scaled_gain_db))
        target_peak_db = -abs(peak_margin_db)
        status_var.set(
            f"Peak analysis: source max {format_db(max_volume_db)} dB, "
            f"target {format_db(target_peak_db)} dB, "
            f"encoded peak {format_db(encoded_peak_db)} dB, "
            f"refined {format_db(recommended_gain_db)} dB, "
            f"scaled initial {format_db(scaled_gain_db)} dB."
        )
        update_command_preview()

    def open_output_folder() -> None:
        output_dir = last_output_folder[0]
        if output_dir is None or not output_dir.is_dir():
            status_var.set("No generated output folder to open.")
            open_output_button.state(["disabled"])
            return
        os.startfile(str(output_dir))

    def open_ffmpeg_folder() -> None:
        tool_status = check_ffmpeg_tools()
        ffmpeg_status_var.set(tool_status.ffmpeg.display_text())
        ffprobe_status_var.set(tool_status.ffprobe.display_text())
        if not tool_status.ffmpeg.available or tool_status.ffmpeg.path is None:
            status_var.set("FFmpeg folder unavailable: ffmpeg is missing.")
            return

        try:
            os.startfile(str(tool_status.ffmpeg.path.parent))
        except OSError as error:
            status_var.set(f"Could not open FFmpeg folder: {error}")

    def run_conversion() -> None:
        try:
            source_text = file_path_var.get().strip()
            output_text = output_folder_var.get().strip()
            min_db = float(min_db_var.get())
            db_interval = float(db_interval_var.get())
            step_count = calculate_step_count(min_db=min_db, db_interval=db_interval)
        except ValueError as error:
            status_var.set(f"Invalid settings: {error}")
            return

        try:
            initial_gain_db = float(initial_gain_db_var.get())
        except ValueError:
            status_var.set("Enter the initial dB value determined in GoldWave.")
            return

        if not source_text:
            status_var.set("Select an input file.")
            return
        if not output_text:
            status_var.set("Select an output folder.")
            return

        source_path = Path(source_text)
        output_dir = Path(output_text)
        if not source_path.is_file():
            status_var.set("Select a valid input file.")
            return
        last_output_folder[0] = None
        open_output_button.state(["disabled"])
        audio_info = get_audio_info(source_path)
        if audio_info is None:
            status_var.set("Cannot read input audio settings with ffprobe.")
            return
        if ENCODER_MODE_LABELS[encoder_mode_choice_var.get()] == ENCODER_MODE_BITRATE and audio_info.bit_rate is None:
            status_var.set("Input audio bitrate is unknown; conversion stopped to avoid changing it.")
            return

        tool_status = check_ffmpeg_tools()
        ffmpeg_status_var.set(tool_status.ffmpeg.display_text())
        ffprobe_status_var.set(tool_status.ffprobe.display_text())
        if not tool_status.available or tool_status.ffmpeg.path is None:
            status_var.set(
                "ffmpeg/ffprobe unavailable. Add both under "
                "vendor/ffmpeg/win-x64/bin or install them on PATH."
            )
            return

        output_dir.mkdir(parents=True, exist_ok=True)
        plan = build_output_plan(
            source_path=source_path,
            output_dir=output_dir,
            db_offset=initial_gain_db,
            step_count=step_count,
            db_interval=-abs(db_interval),
        )
        existing_outputs = [item.output_path for item in plan if item.output_path.exists()]
        if existing_outputs and not overwrite_var.get():
            status_var.set(
                f"{len(existing_outputs)} output files already exist. Enable overwrite or choose a new folder."
            )
            return
        options = get_ffmpeg_options(audio_info, overwrite_var.get())

        for item in plan:
            status_var.set(f"Converting {item.output_path.name}...")
            root.update_idletasks()
            result = convert_plan_item(
                ffmpeg_path=tool_status.ffmpeg.path,
                source_path=source_path,
                item=item,
                options=options,
            )
            if result.returncode != 0:
                error_text = result.stderr.strip() or result.stdout.strip()
                status_var.set(f"ffmpeg failed on {item.output_path.name}: {error_text}")
                return

        last_output_folder[0] = output_dir
        open_output_button.state(["!disabled"])
        status_var.set(f"Generated {len(plan)} files in {output_dir}.")

    ttk.Label(
        frame,
        text="Select input, adjust settings, then choose an output folder.",
        style="Muted.TLabel",
    ).grid(row=0, column=0, sticky="w")
    tools_frame = ttk.Frame(frame)
    tools_frame.grid(row=0, column=0, sticky="e")
    ttk.Label(tools_frame, text="Modules Loaded", style="Muted.TLabel").grid(
        row=0,
        column=0,
        columnspan=2,
        sticky="ew",
        pady=(0, 4),
    )
    ttk.Label(tools_frame, textvariable=ffmpeg_status_var, style="Status.TLabel").grid(
        row=1,
        column=0,
        sticky="e",
    )
    ttk.Label(tools_frame, textvariable=ffprobe_status_var, style="Status.TLabel").grid(
        row=1,
        column=1,
        sticky="e",
        padx=(8, 0),
    )

    input_frame = ttk.Frame(frame)
    input_frame.grid(row=1, column=0, sticky="ew", pady=(16, 0))
    input_frame.columnconfigure(1, weight=1)

    ttk.Label(input_frame, text="Input file").grid(row=0, column=0, sticky="w")
    ttk.Entry(input_frame, textvariable=file_path_var, justify="left").grid(
        row=0,
        column=1,
        sticky="ew",
        padx=(8, 8),
    )
    browse_btn = ttk.Button(input_frame, text="Browse...", command=browse_file)
    browse_btn.grid(row=0, column=2, sticky="e")
    ttk.Label(input_frame, textvariable=audio_info_var, style="Muted.TLabel").grid(
        row=1,
        column=1,
        columnspan=2,
        sticky="w",
        pady=(6, 0),
    )

    settings_frame = ttk.Frame(frame)
    settings_frame.grid(row=2, column=0, sticky="new", pady=(20, 0))
    for column in range(4):
        settings_frame.columnconfigure(column, weight=1, uniform="settings")

    min_db_frame = ttk.Frame(settings_frame)
    min_db_frame.grid(row=0, column=0, sticky="w", padx=(0, 12))
    ttk.Label(min_db_frame, text="Maximum dB").grid(row=0, column=0, sticky="w")
    ttk.Label(min_db_frame, textvariable=max_db_var, width=12, anchor="e").grid(
        row=1,
        column=0,
        sticky="ew",
        pady=(CONTROL_TITLE_GAP_PX, 8),
    )
    ttk.Label(min_db_frame, text="Minimum dB").grid(row=2, column=0, sticky="w")
    min_db_entry = ttk.Entry(
        min_db_frame,
        textvariable=min_db_var,
        width=12,
        justify="right",
    )
    min_db_entry.grid(
        row=3,
        column=0,
        sticky="w",
        pady=(CONTROL_TITLE_GAP_PX, 0),
    )
    min_db_entry.bind("<FocusOut>", lambda _event: format_decimal_var(min_db_var))

    db_interval_frame = ttk.Frame(settings_frame)
    db_interval_frame.grid(row=0, column=1, sticky="w", padx=(0, 12))
    ttk.Label(db_interval_frame, text="dB interval").grid(row=0, column=0, sticky="w")
    db_interval_entry = ttk.Entry(
        db_interval_frame,
        textvariable=db_interval_var,
        width=12,
        justify="right",
    )
    db_interval_entry.grid(row=1, column=0, sticky="w", pady=(CONTROL_TITLE_GAP_PX, 8))
    db_interval_entry.bind("<FocusOut>", lambda _event: format_decimal_var(db_interval_var))
    ttk.Label(db_interval_frame, text="Number of files").grid(row=2, column=0, sticky="w")
    ttk.Label(db_interval_frame, textvariable=step_count_var, width=12, anchor="e").grid(
        row=3,
        column=0,
        sticky="ew",
        pady=(8, 0),
    )

    initial_gain_db_frame = ttk.Frame(settings_frame)
    initial_gain_db_frame.grid(row=0, column=2, sticky="w", padx=(0, 12))
    initial_gain_db_frame.columnconfigure(1, weight=1)
    ttk.Label(initial_gain_db_frame, text="Initial dB").grid(row=0, column=0, sticky="w")
    initial_gain_db_entry = ttk.Entry(
        initial_gain_db_frame,
        textvariable=initial_gain_db_var,
        width=12,
        justify="right",
    )
    initial_gain_db_entry.grid(row=1, column=0, sticky="w", pady=(CONTROL_TITLE_GAP_PX, 0))
    initial_gain_db_entry.bind("<FocusOut>", lambda _event: format_decimal_var(initial_gain_db_var))
    ttk.Button(
        initial_gain_db_frame,
        text="Analyze peak",
        command=analyze_peak,
    ).grid(row=2, column=0, sticky="w", pady=(6, 0))
    ttk.Label(initial_gain_db_frame, text="Pass peaks").grid(
        row=2,
        column=1,
        sticky="w",
        padx=(12, 0),
        pady=(6, 0),
    )
    ttk.Label(
        initial_gain_db_frame,
        textvariable=peak_analysis_results_var,
        style="Muted.TLabel",
        width=12,
        justify="left",
    ).grid(row=3, column=1, rowspan=5, sticky="nw", padx=(12, 0), pady=(CONTROL_TITLE_GAP_PX, 0))
    ttk.Label(initial_gain_db_frame, text="Peak scale").grid(row=3, column=0, sticky="w", pady=(8, 0))
    peak_refinement_scale_entry = ttk.Entry(
        initial_gain_db_frame,
        textvariable=peak_refinement_scale_var,
        width=12,
        justify="right",
    )
    peak_refinement_scale_entry.grid(row=4, column=0, sticky="w", pady=(CONTROL_TITLE_GAP_PX, 0))
    peak_refinement_scale_entry.bind("<FocusOut>", lambda _event: on_peak_scale_focus_out())

    peak_margin_db_frame = ttk.Frame(settings_frame)
    peak_margin_db_frame.grid(row=0, column=3, sticky="w")
    ttk.Label(peak_margin_db_frame, text="Peak margin dB").grid(row=0, column=0, sticky="w")
    peak_margin_db_entry = ttk.Entry(
        peak_margin_db_frame,
        textvariable=peak_margin_db_var,
        width=12,
        justify="right",
    )
    peak_margin_db_entry.grid(row=1, column=0, sticky="w", pady=(CONTROL_TITLE_GAP_PX, 0))
    peak_margin_db_entry.bind("<FocusOut>", lambda _event: on_peak_margin_focus_out())

    min_db_var.trace_add("write", update_step_count)
    db_interval_var.trace_add("write", update_step_count)
    db_interval_var.trace_add("write", update_command_preview)
    initial_gain_db_var.trace_add("write", update_command_preview)
    overwrite_var.trace_add("write", update_command_preview)
    encoder_mode_choice_var.trace_add("write", update_command_preview)
    vorbis_quality_var.trace_add("write", update_vorbis_quality_markers)
    vorbis_quality_var.trace_add("write", update_command_preview)
    update_step_count()
    update_command_preview()

    audio_frame = ttk.Frame(frame)
    audio_frame.grid(row=3, column=0, sticky="ew", pady=(10, 0))
    audio_frame.columnconfigure(0, weight=1)

    encoder_frame = ttk.Frame(audio_frame)
    encoder_frame.grid(row=0, column=0, sticky="ew")
    encoder_frame.columnconfigure(1, weight=1)
    ttk.Label(encoder_frame, text="Encoder mode").grid(row=0, column=0, sticky="w")
    ttk.Combobox(
        encoder_frame,
        textvariable=encoder_mode_choice_var,
        values=tuple(ENCODER_MODE_LABELS),
        state="readonly",
        width=22,
    ).grid(row=1, column=0, sticky="w", pady=(CONTROL_TITLE_GAP_PX, 0))
    quality_scale_frame = ttk.Frame(encoder_frame)
    quality_scale_frame.grid(row=1, column=1, sticky="ew", padx=(32, 0), pady=(4, 0))
    ttk.Label(
        quality_scale_frame,
        text="q\nkbps",
        style="Muted.TLabel",
        anchor="center",
        justify="center",
    ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
    for column, quality in enumerate(VORBIS_QUALITY_VALUES, start=1):
        quality_scale_frame.columnconfigure(column, weight=1, uniform="vorbis_quality")
        quality_label = ttk.Label(
            quality_scale_frame,
            text=f"{format_quality_value(quality)}\n{format_quality_bitrate(quality)}",
            style="Muted.TLabel",
            anchor="center",
            justify="center",
        )
        quality_label.grid(row=0, column=column, sticky="ew")
        vorbis_quality_labels.append(quality_label)
    tk.Scale(
        quality_scale_frame,
        variable=vorbis_quality_var,
        from_=min(VORBIS_QUALITY_VALUES),
        to=max(VORBIS_QUALITY_VALUES),
        orient="horizontal",
        resolution=0.5,
        showvalue=False,
        length=330,
        highlightthickness=0,
    ).grid(row=1, column=1, columnspan=len(VORBIS_QUALITY_VALUES), sticky="ew")
    update_vorbis_quality_markers()

    command_frame = ttk.Frame(frame)
    command_frame.grid(row=4, column=0, sticky="ew", pady=(16, 0))
    command_frame.columnconfigure(0, weight=1)

    ttk.Label(command_frame, text="FFmpeg command").grid(row=0, column=0, sticky="w")
    ttk.Button(
        command_frame,
        text="Open FFmpeg folder",
        command=open_ffmpeg_folder,
    ).grid(row=0, column=1, sticky="e")
    ttk.Entry(
        command_frame,
        textvariable=command_preview_var,
        justify="left",
        state="readonly",
    ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(CONTROL_TITLE_GAP_PX, 0))

    output_frame = ttk.Frame(frame)
    output_frame.grid(row=5, column=0, sticky="ew", pady=(20, 0))
    output_frame.columnconfigure(1, weight=1)

    ttk.Label(output_frame, text="Output folder").grid(row=0, column=0, sticky="w")
    ttk.Entry(
        output_frame,
        textvariable=output_folder_var,
        justify="left",
    ).grid(row=0, column=1, sticky="ew", padx=(8, 8))
    ttk.Button(
        output_frame,
        text="Browse...",
        command=browse_output_folder,
    ).grid(row=0, column=2, sticky="e")

    action_frame = ttk.Frame(frame)
    action_frame.grid(row=6, column=0, sticky="ew", pady=(16, 0))
    action_frame.columnconfigure(0, weight=1)

    ttk.Checkbutton(
        action_frame,
        text="Overwrite existing files",
        variable=overwrite_var,
    ).grid(row=0, column=1, sticky="e", padx=(8, 0))
    ttk.Button(action_frame, text="Run conversion", command=run_conversion).grid(
        row=0,
        column=2,
        sticky="e",
        padx=(8, 0),
    )
    open_output_button = ttk.Button(
        action_frame,
        text="Open output folder",
        command=open_output_folder,
    )
    open_output_button.grid(
        row=0,
        column=3,
        sticky="e",
        padx=(8, 0),
    )
    open_output_button.state(["disabled"])

    refresh_tool_status()

    root.mainloop()


if __name__ == "__main__":
    main()
