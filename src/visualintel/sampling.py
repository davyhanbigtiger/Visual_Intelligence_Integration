from dataclasses import dataclass
import math


@dataclass
class ChunkPlan:
    chunk_index: int
    frame_indices: list[int]
    start_time: float
    end_time: float


def plan_chunks(
    total_frames: int,
    fps: float,
    interval_sec: float = 2.0,
    max_frames_per_chunk: int = 8,
    max_chunks: int = 20,
) -> tuple[list[ChunkPlan], bool]:
    """Sample frames at a fixed interval and group them into chunks.

    Returns (chunks, truncated) where truncated is True if the video had
    more sample points than max_chunks * max_frames_per_chunk could hold.
    """
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError("fps must be finite and positive")
    if not math.isfinite(interval_sec) or interval_sec <= 0 or max_frames_per_chunk <= 0 or max_chunks <= 0:
        raise ValueError("sampling limits must be positive")
    if total_frames <= 0:
        return [], False

    step = max(1, round(fps * interval_sec))
    samples = range(0, total_frames, step)

    max_indices = max_frames_per_chunk * max_chunks
    truncated = len(samples) > max_indices
    indices = list(samples[:max_indices])

    chunks: list[ChunkPlan] = []
    for chunk_index, start in enumerate(range(0, len(indices), max_frames_per_chunk)):
        frame_indices = indices[start:start + max_frames_per_chunk]
        chunks.append(
            ChunkPlan(
                chunk_index=chunk_index,
                frame_indices=frame_indices,
                start_time=frame_indices[0] / fps,
                end_time=frame_indices[-1] / fps,
            )
        )
    return chunks, truncated


def plan_single_chunk_over_video(
    total_frames: int,
    fps: float,
    max_frames: int = 8,
) -> ChunkPlan:
    """Evenly sample up to max_frames across the whole video as one chunk.

    Used for the `ask` command, which answers questions about the whole
    clip rather than a specific time range.
    """
    if not math.isfinite(fps) or fps <= 0 or max_frames <= 0:
        raise ValueError("fps and max_frames must be positive and finite")
    if total_frames <= 0:
        return ChunkPlan(chunk_index=0, frame_indices=[], start_time=0.0, end_time=0.0)

    n = min(max_frames, total_frames)
    if n == 1:
        frame_indices = [0]
    else:
        frame_indices = [round(i * (total_frames - 1) / (n - 1)) for i in range(n)]

    return ChunkPlan(
        chunk_index=0,
        frame_indices=frame_indices,
        start_time=frame_indices[0] / fps,
        end_time=frame_indices[-1] / fps,
    )
