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
    APP_NAME,
    APP_ROW_GAP_PX,
    CONTROL_TITLE_GAP_PX,
    COMPACT_SECTION_ROW_GAP_PX,
    DB_DISPLAY_DECIMALS,
    DB_FIELD_WIDTH_CHARS,
    DEFAULT_CALCULATED_GAIN_DB_TEXT,
    DEFAULT_FILE_COUNT,
    DEFAULT_INTERVAL_DB,
    DEFAULT_ENCODER_MODE,
    DEFAULT_MIN_DB,
    DEFAULT_PEAK_HEADROOM_DB,
    DEFAULT_VORBIS_QUALITY,
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    BUTTON_PAD_X_PX,
    CALCULATED_GAIN_LABEL_WIDTH_CHARS,
    ENCODER_MODE_BITRATE,
    ENCODER_MODE_QUALITY,
    ENCODER_MODE_WIDTH_CHARS,
    DB_LABEL_WIDTH_CHARS,
    ENCODER_SCALE_PAD_X_PX,
    FIELD_PAD_X_PX,
    RELATED_CONTROL_GAP_PX,
    SETTINGS_COLUMN_COUNT,
    VORBIS_SCALE_LENGTH_PX,
    VORBIS_QUALITY_BITRATES,
    get_runtime_paths,
)
from audiofix.core.analysis import (
    PeakAnalysisRequest,
    PeakAnalysisResult,
    analyze_peak as run_peak_analysis,
)
from audiofix.core.conversion import (
    ConversionProgress,
    ConversionRequest,
    ConversionResult,
    run_conversion_request,
)
from audiofix.core.ffmpeg import (
    FfmpegOptions,
    AudioInfo,
    ToolStatus,
    build_ffmpeg_command,
    check_ffmpeg_tools,
    probe_audio_info,
)
from audiofix.core.logging import (
    ConversionLogSettings,
)
from audiofix.core.planning import (
    build_output_plan,
    calculate_interval_db,
    calculate_step_count,
)
from audiofix.core.tasks import start_background_task
from audiofix.gui.theme import DEFAULT_THEME, THEMES, apply_theme

VORBIS_QUALITY_VALUES = [value / 2 for value in range(-2, 21)]
ENCODER_MODE_LABELS = {
    "Vorbis Quality": ENCODER_MODE_QUALITY,
    "Match Source Bitrate": ENCODER_MODE_BITRATE,
}
ENCODER_MODE_NAMES = {value: label for label, value in ENCODER_MODE_LABELS.items()}
LEVEL_INPUT_FILE_COUNT = "File Count"
LEVEL_INPUT_INTERVAL_DB = "Interval dB"


def format_quality_value(quality: float) -> str:
    return f"{quality:g}"


def format_quality_bitrate(quality: float) -> str:
    if quality.is_integer():
        return VORBIS_QUALITY_BITRATES[int(quality)].split()[0]
    return ""


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
        label=f"About {APP_NAME}",
        command=lambda: messagebox.showinfo(
            title=f"About {APP_NAME}",
            message=(
                f"{APP_NAME} {__version__}\n\n"
                "Batch loudness converter for generating quieter game audio variants."
            ),
        ),
    )
    menu_bar.add_cascade(label="Help", menu=help_menu)

    return menu_bar


def main() -> None:
    root = tk.Tk()
    root.title(APP_NAME)
    root.geometry(f"{DEFAULT_WINDOW_WIDTH}x{DEFAULT_WINDOW_HEIGHT}")
    root.minsize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
    apply_theme(root, DEFAULT_THEME)

    frame = ttk.Frame(root, padding=16)
    frame.grid(row=0, column=0, sticky="nsew")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)

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
    min_db_var = tk.StringVar(value="")
    calculated_gain_db_var = tk.StringVar(value=DEFAULT_CALCULATED_GAIN_DB_TEXT)
    interval_db_var = tk.StringVar(value="")
    level_input_mode_var = tk.StringVar(value=LEVEL_INPUT_FILE_COUNT)
    peak_headroom_db_var = tk.StringVar(value="")
    step_count_var = tk.StringVar(value="")
    output_path_var = tk.StringVar(value="")
    audio_info_var = tk.StringVar(value="Audio info: select an input file.")
    raw_peak_var = tk.StringVar(value="Raw peak: --")
    overwrite_var = tk.BooleanVar(value=False)
    disable_gain_adjustment_var = tk.BooleanVar(value=False)
    encoder_mode_choice_var = tk.StringVar(value=ENCODER_MODE_NAMES[DEFAULT_ENCODER_MODE])
    vorbis_quality_var = tk.DoubleVar(value=DEFAULT_VORBIS_QUALITY)
    vorbis_quality_labels: list[ttk.Label] = []
    status_var = tk.StringVar(value="Ready.")
    ffmpeg_status_var = tk.StringVar(value="")
    ffprobe_status_var = tk.StringVar(value="")
    command_preview_var = tk.StringVar(value="ffmpeg command preview unavailable.")
    progress_var = tk.DoubleVar(value=0)
    last_audio_info: list[AudioInfo | None] = [None]
    last_output_folder: list[Path | None] = [None]
    peak_analysis_running = [False]
    conversion_running = [False]
    tool_status_cache: list[ToolStatus | None] = [None]

    def format_db(value: float, signed: bool = False) -> str:
        sign = "+" if signed else ""
        return f"{value:{sign}.{DB_DISPLAY_DECIMALS}f}"

    min_db_var.set(format_db(DEFAULT_MIN_DB))
    interval_db_var.set(format_db(DEFAULT_INTERVAL_DB))
    step_count_var.set(str(DEFAULT_FILE_COUNT))
    peak_headroom_db_var.set(format_db(DEFAULT_PEAK_HEADROOM_DB))

    def update_tool_status():
        tool_status = check_ffmpeg_tools()
        set_tool_status(tool_status)
        return tool_status

    def set_tool_status(tool_status: ToolStatus) -> None:
        tool_status_cache[0] = tool_status
        ffmpeg_status_var.set(tool_status.ffmpeg.display_text())
        ffprobe_status_var.set(tool_status.ffprobe.display_text())

    def refresh_tool_status() -> None:
        update_tool_status()

    def get_cached_tool_status() -> ToolStatus:
        return tool_status_cache[0] or update_tool_status()

    def schedule_ui(callback) -> None:
        root.after(0, callback)

    def format_audio_info(info: AudioInfo) -> str:
        bit_rate = f"{round(info.bit_rate / 1000)} kbps" if info.bit_rate else "unknown bitrate"
        sample_rate = f"{info.sample_rate} Hz" if info.sample_rate else "unknown sample rate"
        channels = f"{info.channels} ch" if info.channels else "unknown channels"
        return f"Audio info: {info.codec_name}, {bit_rate}, {sample_rate}, {channels}"

    def parse_output_target() -> tuple[Path, str]:
        output_text = output_path_var.get().strip()
        if not output_text:
            raise ValueError("enter an output path")

        output_target = Path(output_text)
        output_stem = output_target.stem if output_target.suffix else output_target.name
        if not output_stem:
            raise ValueError("output filename must not be empty")
        return output_target.parent, output_stem

    def get_audio_info(source_path: Path, tool_status: ToolStatus | None = None) -> AudioInfo | None:
        tool_status = tool_status or update_tool_status()
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

    def parse_step_count() -> int:
        raw_step_count = float(step_count_var.get())
        step_count = int(raw_step_count)
        if step_count != raw_step_count:
            raise ValueError("file count must be a whole number")
        return step_count

    def calculate_level_settings() -> tuple[float, float, int]:
        min_db = float(min_db_var.get())
        if level_input_mode_var.get() == LEVEL_INPUT_INTERVAL_DB:
            interval_db = float(interval_db_var.get())
            step_count = calculate_step_count(min_db=min_db, interval_db=interval_db)
            return min_db, interval_db, step_count

        step_count = parse_step_count()
        interval_db = calculate_interval_db(min_db=min_db, step_count=step_count)
        return min_db, interval_db, step_count

    updating_level_fields = [False]

    def update_level_fields(*_: object) -> None:
        if updating_level_fields[0]:
            return

        updating_level_fields[0] = True
        try:
            _min_db, interval_db, step_count = calculate_level_settings()
        except ValueError:
            if level_input_mode_var.get() == LEVEL_INPUT_INTERVAL_DB:
                step_count_var.set("Invalid")
            else:
                interval_db_var.set("Invalid")
        else:
            if level_input_mode_var.get() == LEVEL_INPUT_INTERVAL_DB:
                step_count_var.set(str(step_count))
            else:
                interval_db_var.set(format_db(interval_db))
        finally:
            updating_level_fields[0] = False

        update_command_preview()

    def update_level_input_mode(*_: object) -> None:
        if level_input_mode_var.get() == LEVEL_INPUT_INTERVAL_DB:
            interval_db_entry.state(["!disabled"])
            step_count_entry.state(["disabled"])
        else:
            interval_db_entry.state(["disabled"])
            step_count_entry.state(["!disabled"])
        update_level_fields()

    def on_interval_db_focus_out() -> None:
        if level_input_mode_var.get() != LEVEL_INPUT_INTERVAL_DB:
            return
        format_decimal_var(interval_db_var)
        update_level_fields()

    def on_step_count_focus_out() -> None:
        if level_input_mode_var.get() != LEVEL_INPUT_FILE_COUNT:
            return
        try:
            step_count_var.set(str(parse_step_count()))
        except ValueError:
            return
        update_level_fields()

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
        if not source_text or not output_path_var.get().strip():
            command_preview_var.set("ffmpeg command preview unavailable.")
            return

        tool_status = get_cached_tool_status()
        if not tool_status.ffmpeg.available or tool_status.ffmpeg.path is None:
            command_preview_var.set("ffmpeg command preview unavailable: ffmpeg missing.")
            return

        try:
            _min_db, interval_db, _step_count = calculate_level_settings()
        except ValueError:
            command_preview_var.set("ffmpeg command preview unavailable: enter valid level settings.")
            return

        if disable_gain_adjustment_var.get():
            calculated_gain_db = 0.0
        else:
            try:
                calculated_gain_db = float(calculated_gain_db_var.get())
            except ValueError:
                command_preview_var.set("ffmpeg command preview unavailable: enter raw plus headroom dB.")
                return

        try:
            output_dir, output_stem = parse_output_target()
        except ValueError:
            command_preview_var.set("ffmpeg command preview unavailable: enter valid output path.")
            return

        source_path = Path(source_text)
        plan = build_output_plan(
            source_path=source_path,
            output_dir=output_dir,
            db_offset=calculated_gain_db,
            step_count=1,
            interval_db=-abs(interval_db),
            output_stem=output_stem,
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

    def add_db_entry(
        parent: ttk.Frame,
        label: str,
        value_var: tk.StringVar,
        row: int,
        column: int,
        bottom_gap: int = 0,
        label_anchor: str = "center",
        label_sticky: str = "w",
        label_width: int = DB_LABEL_WIDTH_CHARS,
    ) -> ttk.Entry:
        ttk.Label(
            parent,
            text=label,
            anchor=label_anchor,
            width=label_width,
        ).grid(
            row=row,
            column=column,
            sticky=label_sticky,
        )
        entry = ttk.Entry(
            parent,
            textvariable=value_var,
            width=DB_FIELD_WIDTH_CHARS,
            justify="right",
        )
        entry.grid(
            row=row + 1,
            column=column,
            sticky="w",
            pady=(CONTROL_TITLE_GAP_PX, bottom_gap),
        )
        entry.bind("<FocusOut>", lambda _event: format_decimal_var(value_var))
        return entry

    def reset_peak_analysis(message: str) -> None:
        raw_peak_var.set("Raw peak: --")
        status_var.set(message)

    def clear_generated_output_state() -> None:
        last_output_folder[0] = None
        open_output_button.state(["disabled"])

    def set_peak_analysis_controls_enabled(enabled: bool) -> None:
        state = ["!disabled"] if enabled else ["disabled"]
        input_file_entry.state(state)
        input_browse_button.state(state)
        gain_adjustment_checkbutton.state(state)
        gain_state = state if not disable_gain_adjustment_var.get() else ["disabled"]
        peak_headroom_db_entry.state(gain_state)
        encoder_mode_combobox.state(["readonly"] if enabled else ["disabled"])
        analyze_peak_button.state(state)

    def set_conversion_controls_enabled(enabled: bool) -> None:
        state = ["!disabled"] if enabled else ["disabled"]
        input_file_entry.state(state)
        input_browse_button.state(state)
        min_db_entry.state(state)
        interval_input_radio.state(state)
        file_count_input_radio.state(state)
        if enabled:
            update_level_input_mode()
        else:
            interval_db_entry.state(["disabled"])
            step_count_entry.state(["disabled"])
        gain_adjustment_checkbutton.state(state)
        gain_state = state if not disable_gain_adjustment_var.get() else ["disabled"]
        peak_headroom_db_entry.state(gain_state)
        calculated_gain_db_entry.state(gain_state)
        analyze_peak_button.state(state)
        encoder_mode_combobox.state(["readonly"] if enabled else ["disabled"])
        quality_scale.configure(state="normal" if enabled else "disabled")
        output_path_entry.state(state)
        output_browse_button.state(state)
        overwrite_checkbutton.state(state)
        run_conversion_button.state(state)

    def on_peak_headroom_focus_out() -> None:
        if disable_gain_adjustment_var.get():
            return
        if not peak_headroom_db_var.get().strip():
            peak_headroom_db_var.set(format_db(DEFAULT_PEAK_HEADROOM_DB))
        format_decimal_var(peak_headroom_db_var)
        reset_peak_analysis("Headroom changed. Click Analyze peak to recalculate raw plus headroom dB.")

    def update_gain_adjustment_mode(*_: object) -> None:
        gain_controls_enabled = (
            not disable_gain_adjustment_var.get()
            and not peak_analysis_running[0]
            and not conversion_running[0]
        )
        gain_state = ["!disabled"] if gain_controls_enabled else ["disabled"]
        peak_headroom_db_entry.state(gain_state)
        calculated_gain_db_entry.state(gain_state)
        analyze_state = ["disabled"] if peak_analysis_running[0] or conversion_running[0] else ["!disabled"]
        analyze_peak_button.state(analyze_state)
        if not disable_gain_adjustment_var.get():
            if not calculated_gain_db_var.get().strip():
                reset_peak_analysis("Peak/headroom gain enabled. Click Analyze peak to calculate raw plus headroom dB.")
        else:
            status_var.set(
                "Peak/headroom gain disabled. Analyze peak still records raw peak; files step down by interval."
            )
        update_command_preview()

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
            output_path_var.set(str(input_path.with_name(f"{input_path.stem}_out") / input_path.stem))
            last_audio_info[0] = None
            raw_peak_var.set("Raw peak: --")
            clear_generated_output_state()
            analyze_peak()

    def browse_output_folder() -> None:
        path = filedialog.askdirectory(
            title="Select output folder",
            initialdir=str(media_dir),
        )
        if path:
            try:
                _output_dir, output_stem = parse_output_target()
            except ValueError:
                source_text = file_path_var.get().strip()
                output_stem = Path(source_text).stem if source_text else "output"
            output_path_var.set(str(Path(path) / output_stem))
            clear_generated_output_state()
            update_command_preview()

    def analyze_peak() -> None:
        if peak_analysis_running[0]:
            status_var.set("Peak analysis is already running.")
            return

        source_text = file_path_var.get().strip()
        if not source_text:
            status_var.set("Select an input file before analyzing peak.")
            return

        source_path = Path(source_text)
        if not source_path.is_file():
            status_var.set("Select a valid input file before analyzing peak.")
            return

        try:
            headroom_db = float(peak_headroom_db_var.get())
        except ValueError:
            if not disable_gain_adjustment_var.get():
                status_var.set("Enter a valid headroom dB value.")
                return
            headroom_db = DEFAULT_PEAK_HEADROOM_DB

        encoder_mode = ENCODER_MODE_LABELS[encoder_mode_choice_var.get()]
        peak_analysis_running[0] = True
        set_peak_analysis_controls_enabled(False)
        status_var.set("Analyzing peak...")
        request = PeakAnalysisRequest(
            source_path=source_path,
            headroom_db=headroom_db,
            encoder_mode=encoder_mode,
        )
        start_background_task(
            work=lambda: run_peak_analysis(request),
            on_success=finish_peak_analysis,
            on_error=fail_peak_analysis,
            schedule=schedule_ui,
        )

    def fail_peak_analysis(error: Exception) -> None:
        peak_analysis_running[0] = False
        set_peak_analysis_controls_enabled(True)
        status_var.set(f"Peak analysis failed: {error}")

    def finish_peak_analysis(result: PeakAnalysisResult) -> None:
        peak_analysis_running[0] = False
        set_peak_analysis_controls_enabled(True)
        set_tool_status(result.tool_status)
        audio_info_var.set(format_audio_info(result.audio_info))
        last_audio_info[0] = result.audio_info
        raw_peak_var.set(f"Raw peak: {format_db(result.max_volume_db, signed=True)} dB")
        peak_target_db = -abs(result.headroom_db)
        calculated_gain_db_var.set(format_db(result.calculated_gain_db))
        if disable_gain_adjustment_var.get():
            status_var.set(
                f"Peak analysis: source max {format_db(result.max_volume_db)} dB. "
                "Peak/headroom gain is disabled, so raw plus headroom is ignored for conversion."
            )
            update_command_preview()
            return
        status_var.set(
            f"Peak analysis: source max {format_db(result.max_volume_db)} dB, "
            f"target {format_db(peak_target_db)} dB, "
            f"headroom {format_db(abs(result.headroom_db))} dB, "
            f"raw plus headroom {format_db(result.calculated_gain_db)} dB."
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
        tool_status = update_tool_status()
        if not tool_status.ffmpeg.available or tool_status.ffmpeg.path is None:
            status_var.set("FFmpeg folder unavailable: ffmpeg is missing.")
            return

        try:
            os.startfile(str(tool_status.ffmpeg.path.parent))
        except OSError as error:
            status_var.set(f"Could not open FFmpeg folder: {error}")

    def run_conversion() -> None:
        if peak_analysis_running[0]:
            status_var.set("Wait for peak analysis to finish before running conversion.")
            return
        if conversion_running[0]:
            status_var.set("Conversion is already running.")
            return

        try:
            source_text = file_path_var.get().strip()
            output_dir, output_stem = parse_output_target()
            min_db, interval_db, step_count = calculate_level_settings()
            update_level_fields()
        except ValueError as error:
            status_var.set(f"Invalid settings: {error}")
            return

        if not disable_gain_adjustment_var.get():
            try:
                headroom_db: float | None = float(peak_headroom_db_var.get())
            except ValueError as error:
                status_var.set(f"Invalid settings: {error}")
                return

            try:
                calculated_gain_db: float | None = float(calculated_gain_db_var.get())
            except ValueError:
                status_var.set("Analyze peak or enter raw plus headroom dB.")
                return
        else:
            headroom_db = None
            calculated_gain_db = None

        if not source_text:
            status_var.set("Select an input file.")
            return

        source_path = Path(source_text)
        if not source_path.is_file():
            status_var.set("Select a valid input file.")
            return
        clear_generated_output_state()
        tool_status = update_tool_status()
        if not tool_status.available or tool_status.ffmpeg.path is None:
            status_var.set(
                "ffmpeg/ffprobe unavailable. Add both under "
                "vendor/ffmpeg/win-x64/bin or install them on PATH."
            )
            return
        if tool_status.ffprobe.path is None:
            status_var.set("ffprobe unavailable; cannot validate generated files.")
            return

        audio_info = get_audio_info(source_path, tool_status)
        if audio_info is None:
            status_var.set("Cannot read input audio settings with ffprobe.")
            return
        if ENCODER_MODE_LABELS[encoder_mode_choice_var.get()] == ENCODER_MODE_BITRATE and audio_info.bit_rate is None:
            status_var.set("Input audio bitrate is unknown; conversion stopped to avoid changing it.")
            return

        output_dir.mkdir(parents=True, exist_ok=True)
        plan = build_output_plan(
            source_path=source_path,
            output_dir=output_dir,
            db_offset=calculated_gain_db if calculated_gain_db is not None else 0.0,
            step_count=step_count,
            interval_db=-abs(interval_db),
            output_stem=output_stem,
        )
        existing_outputs = [item.output_path for item in plan if item.output_path.exists()]
        if existing_outputs and not overwrite_var.get():
            status_var.set(
                f"{len(existing_outputs)} output files already exist. Enable overwrite or choose a new folder."
            )
            return
        options = get_ffmpeg_options(audio_info, overwrite_var.get())
        settings = ConversionLogSettings(
            source_path=source_path,
            output_dir=output_dir,
            source_channels=audio_info.channels,
            min_db=min_db,
            interval_db=interval_db,
            raw_peak_db=parse_raw_peak_display(),
            headroom_db=headroom_db,
            calculated_gain_db=calculated_gain_db,
            encoder_mode=encoder_mode_choice_var.get(),
            vorbis_quality=float(vorbis_quality_var.get())
            if ENCODER_MODE_LABELS[encoder_mode_choice_var.get()] == ENCODER_MODE_QUALITY
            else None,
            overwrite=overwrite_var.get(),
            gain_adjustment_enabled=not disable_gain_adjustment_var.get(),
        )

        conversion_running[0] = True
        clear_generated_output_state()
        progress_var.set(0)
        progress_bar.configure(maximum=len(plan), value=0)
        set_conversion_controls_enabled(False)
        status_var.set(f"Starting conversion: 0 of {len(plan)} files.")
        request = ConversionRequest(
            ffmpeg_path=tool_status.ffmpeg.path,
            ffprobe_path=tool_status.ffprobe.path,
            source_path=source_path,
            output_dir=output_dir,
            plan=plan,
            options=options,
            settings=settings,
        )
        start_background_task(
            work=lambda: run_conversion_request(
                request,
                on_progress=lambda progress: schedule_ui(
                    lambda progress=progress: update_conversion_progress(progress)
                ),
            ),
            on_success=finish_conversion,
            on_error=fail_conversion,
            schedule=schedule_ui,
        )

    def fail_conversion(error: Exception) -> None:
        conversion_running[0] = False
        set_conversion_controls_enabled(True)
        status_var.set(f"Conversion failed: {error}")

    def parse_raw_peak_display() -> float | None:
        prefix = "Raw peak:"
        raw_peak_text = raw_peak_var.get()
        if not raw_peak_text.startswith(prefix):
            return None
        value_text = raw_peak_text[len(prefix) :].strip().removesuffix(" dB")
        if value_text == "--":
            return None
        try:
            return float(value_text)
        except ValueError:
            return None

    def update_conversion_progress(progress: ConversionProgress) -> None:
        progress_var.set(progress.completed_count)
        status_var.set(
            f"Converting {progress.completed_count + 1} of {progress.total_count}: {progress.filename}"
        )

    def finish_conversion(result: ConversionResult) -> None:
        conversion_running[0] = False
        set_conversion_controls_enabled(True)
        if result.success:
            progress_var.set(result.total_count)
            last_output_folder[0] = result.output_dir
            open_output_button.state(["!disabled"])
            status_var.set(
                f"Generated {result.total_count} files in {result.output_dir}. "
                f"Log: {result.log_path.name}"
            )
            return

        status_var.set(
            f"Conversion failed after {result.file_count} of {result.total_count} files. "
            f"Log: {result.log_path.name}. {result.failure_message or ''}".strip()
        )

    ttk.Label(
        frame,
        text="Select input, adjust settings, then choose an output path.",
        style="Muted.TLabel",
    ).grid(row=0, column=0, sticky="w")

    def configure_level_columns(container: ttk.Frame) -> None:
        container.columnconfigure(0, weight=1, uniform="settings")
        container.columnconfigure(1, weight=0)
        for column in range(2, SETTINGS_COLUMN_COUNT):
            container.columnconfigure(column, weight=1, uniform="settings")

    tools_frame = ttk.Frame(frame)
    tools_frame.grid(row=0, column=0, sticky="e")
    ttk.Label(tools_frame, text="Modules Loaded", style="Muted.TLabel").grid(
        row=0,
        column=0,
        columnspan=2,
        sticky="ew",
        pady=(0, CONTROL_TITLE_GAP_PX * 2),
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
        padx=(BUTTON_PAD_X_PX, 0),
    )

    input_frame = ttk.Frame(frame)
    input_frame.grid(row=1, column=0, sticky="ew", pady=(APP_ROW_GAP_PX, 0))
    input_frame.columnconfigure(1, weight=1)

    ttk.Label(input_frame, text="Input file").grid(row=0, column=0, sticky="w")
    input_file_entry = ttk.Entry(input_frame, textvariable=file_path_var, justify="left")
    input_file_entry.grid(
        row=0,
        column=1,
        sticky="ew",
        padx=(FIELD_PAD_X_PX, FIELD_PAD_X_PX),
    )
    input_browse_button = ttk.Button(input_frame, text="Browse...", command=browse_file)
    input_browse_button.grid(row=0, column=2, sticky="e")

    input_meta_frame = ttk.Frame(frame)
    input_meta_frame.grid(
        row=2,
        column=0,
        sticky="ew",
        pady=(COMPACT_SECTION_ROW_GAP_PX, 0),
    )
    configure_level_columns(input_meta_frame)
    ttk.Label(input_meta_frame, textvariable=audio_info_var, style="Muted.TLabel").grid(
        row=0,
        column=0,
        columnspan=2,
        sticky="w",
    )
    ttk.Label(
        input_meta_frame,
        textvariable=raw_peak_var,
        style="Muted.TLabel",
        anchor="w",
        width=CALCULATED_GAIN_LABEL_WIDTH_CHARS,
    ).grid(
        row=0,
        column=4,
        sticky="w",
    )

    settings_frame = ttk.Frame(frame)
    settings_frame.grid(row=3, column=0, sticky="new", pady=(APP_ROW_GAP_PX, 0))
    configure_level_columns(settings_frame)

    min_db_entry = add_db_entry(settings_frame, "Minimum dB", min_db_var, row=0, column=0)

    interval_input_radio = ttk.Radiobutton(
        settings_frame,
        variable=level_input_mode_var,
        value=LEVEL_INPUT_INTERVAL_DB,
    )
    interval_input_radio.grid(
        row=1,
        column=1,
        sticky="e",
        padx=(0, CONTROL_TITLE_GAP_PX),
        pady=(CONTROL_TITLE_GAP_PX, RELATED_CONTROL_GAP_PX),
    )
    file_count_input_radio = ttk.Radiobutton(
        settings_frame,
        variable=level_input_mode_var,
        value=LEVEL_INPUT_FILE_COUNT,
    )
    file_count_input_radio.grid(
        row=3,
        column=1,
        sticky="e",
        padx=(0, CONTROL_TITLE_GAP_PX),
        pady=(RELATED_CONTROL_GAP_PX, 0),
    )

    interval_db_entry = add_db_entry(
        settings_frame,
        "Interval dB",
        interval_db_var,
        row=0,
        column=2,
        bottom_gap=RELATED_CONTROL_GAP_PX,
    )
    interval_db_entry.bind("<FocusOut>", lambda _event: on_interval_db_focus_out())
    ttk.Label(
        settings_frame,
        text="File Count",
        anchor="center",
        width=DB_FIELD_WIDTH_CHARS,
    ).grid(row=2, column=2, sticky="w")
    step_count_entry = ttk.Entry(
        settings_frame,
        textvariable=step_count_var,
        width=DB_FIELD_WIDTH_CHARS,
        justify="right",
    )
    step_count_entry.grid(
        row=3,
        column=2,
        sticky="w",
        pady=(RELATED_CONTROL_GAP_PX, 0),
    )
    step_count_entry.bind("<FocusOut>", lambda _event: on_step_count_focus_out())

    peak_headroom_db_entry = add_db_entry(
        settings_frame,
        "Headroom dB",
        peak_headroom_db_var,
        row=0,
        column=3,
        bottom_gap=RELATED_CONTROL_GAP_PX,
    )
    peak_headroom_db_entry.bind("<FocusOut>", lambda _event: on_peak_headroom_focus_out())
    gain_adjustment_checkbutton = ttk.Checkbutton(
        settings_frame,
        text="Disable peak/headroom gain",
        variable=disable_gain_adjustment_var,
    )
    gain_adjustment_checkbutton.grid(row=3, column=3, sticky="w", pady=(CONTROL_TITLE_GAP_PX, 0))

    calculated_gain_db_entry = add_db_entry(
        settings_frame,
        "- (Raw + Head) dB",
        calculated_gain_db_var,
        row=0,
        column=4,
        label_width=CALCULATED_GAIN_LABEL_WIDTH_CHARS,
    )
    analyze_peak_button = ttk.Button(
        settings_frame,
        text="Analyze peak",
        command=analyze_peak,
    )
    analyze_peak_button.grid(row=3, column=4, sticky="w", pady=(CONTROL_TITLE_GAP_PX, 0))

    min_db_var.trace_add("write", update_level_fields)
    step_count_var.trace_add("write", update_level_fields)
    interval_db_var.trace_add("write", update_level_fields)
    level_input_mode_var.trace_add("write", update_level_input_mode)
    calculated_gain_db_var.trace_add("write", update_command_preview)
    overwrite_var.trace_add("write", update_command_preview)
    disable_gain_adjustment_var.trace_add("write", update_gain_adjustment_mode)
    encoder_mode_choice_var.trace_add("write", update_command_preview)
    vorbis_quality_var.trace_add("write", update_vorbis_quality_markers)
    vorbis_quality_var.trace_add("write", update_command_preview)
    update_level_input_mode()
    update_command_preview()

    encoder_frame = ttk.Frame(frame)
    encoder_frame.grid(row=4, column=0, sticky="ew", pady=(APP_ROW_GAP_PX, 0))
    encoder_frame.columnconfigure(1, weight=1)
    ttk.Label(encoder_frame, text="Encoder mode").grid(row=0, column=0, sticky="w")
    encoder_mode_combobox = ttk.Combobox(
        encoder_frame,
        textvariable=encoder_mode_choice_var,
        values=tuple(ENCODER_MODE_LABELS),
        state="readonly",
        width=ENCODER_MODE_WIDTH_CHARS,
    )
    encoder_mode_combobox.grid(row=1, column=0, sticky="nw", pady=(CONTROL_TITLE_GAP_PX, 0))
    quality_scale_frame = ttk.Frame(encoder_frame)
    quality_scale_frame.grid(row=0, column=1, rowspan=2, sticky="ew", padx=(ENCODER_SCALE_PAD_X_PX, 0))
    ttk.Label(
        quality_scale_frame,
        text="q\nkbps",
        style="Muted.TLabel",
        anchor="center",
        justify="center",
    ).grid(row=0, column=0, sticky="ew", padx=(0, COMPACT_SECTION_ROW_GAP_PX))
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
    quality_scale = tk.Scale(
        quality_scale_frame,
        variable=vorbis_quality_var,
        from_=min(VORBIS_QUALITY_VALUES),
        to=max(VORBIS_QUALITY_VALUES),
        orient="horizontal",
        resolution=0.5,
        showvalue=False,
        length=VORBIS_SCALE_LENGTH_PX,
        highlightthickness=0,
    )
    quality_scale.grid(row=1, column=1, columnspan=len(VORBIS_QUALITY_VALUES), sticky="ew")
    update_vorbis_quality_markers()

    command_frame = ttk.Frame(frame)
    command_frame.grid(row=5, column=0, sticky="ew", pady=(APP_ROW_GAP_PX, 0))
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
    output_frame.grid(row=6, column=0, sticky="ew", pady=(APP_ROW_GAP_PX, 0))
    output_frame.columnconfigure(1, weight=1)

    ttk.Label(output_frame, text="Output path").grid(row=0, column=0, sticky="w")
    output_path_entry = ttk.Entry(
        output_frame,
        textvariable=output_path_var,
        justify="left",
    )
    output_path_entry.grid(row=0, column=1, sticky="ew", padx=(FIELD_PAD_X_PX, FIELD_PAD_X_PX))
    output_path_var.trace_add("write", update_command_preview)

    output_browse_button = ttk.Button(
        output_frame,
        text="Browse folder...",
        command=browse_output_folder,
    )
    output_browse_button.grid(row=0, column=2, sticky="e")

    action_frame = ttk.Frame(frame)
    action_frame.grid(row=7, column=0, sticky="ew", pady=(APP_ROW_GAP_PX, 0))
    action_frame.columnconfigure(0, weight=1)

    overwrite_checkbutton = ttk.Checkbutton(
        action_frame,
        text="Overwrite existing files",
        variable=overwrite_var,
    )
    overwrite_checkbutton.grid(row=0, column=1, sticky="e", padx=(BUTTON_PAD_X_PX, 0))
    run_conversion_button = ttk.Button(action_frame, text="Run Conversion", command=run_conversion)
    run_conversion_button.grid(
        row=0,
        column=2,
        sticky="e",
        padx=(BUTTON_PAD_X_PX, 0),
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
        padx=(BUTTON_PAD_X_PX, 0),
    )
    open_output_button.state(["disabled"])
    progress_bar = ttk.Progressbar(
        action_frame,
        variable=progress_var,
        mode="determinate",
    )
    progress_bar.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(RELATED_CONTROL_GAP_PX, 0))

    refresh_tool_status()
    update_gain_adjustment_mode()

    root.mainloop()


if __name__ == "__main__":
    main()
