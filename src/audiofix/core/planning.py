"""Output planning for file count, per-file gain, and numbered output paths."""

from dataclasses import dataclass
import math
from pathlib import Path

from audiofix.core.config import DEFAULT_OUTPUT_EXTENSION


@dataclass(frozen=True)
class OutputPlanItem:
    index: int
    gain_db: float
    output_path: Path


def calculate_step_count(min_db: float, interval_db: float) -> int:
    if min_db >= 0:
        raise ValueError("min_db must be less than 0")
    if interval_db <= 0:
        raise ValueError("interval_db must be greater than 0")

    return math.floor(abs(min_db) / interval_db) + 1


def calculate_interval_db(min_db: float, step_count: int) -> float:
    if min_db >= 0:
        raise ValueError("min_db must be less than 0")
    if step_count < 2:
        raise ValueError("file count must be at least 2")

    return abs(min_db) / (step_count - 1)


def build_output_plan(
    source_path: Path,
    output_dir: Path,
    db_offset: float,
    step_count: int,
    interval_db: float,
    output_extension: str = DEFAULT_OUTPUT_EXTENSION,
) -> list[OutputPlanItem]:
    if step_count < 1:
        raise ValueError("step_count must be at least 1")

    extension = output_extension if output_extension.startswith(".") else f".{output_extension}"
    stem = source_path.stem

    return [
        OutputPlanItem(
            index=index,
            gain_db=db_offset + (index * interval_db),
            output_path=output_dir / f"{stem}_{index}{extension}",
        )
        for index in range(step_count)
    ]
