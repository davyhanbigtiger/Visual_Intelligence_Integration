import pytest

from visualintel.sampling import ChunkPlan, plan_chunks, plan_single_chunk_over_video


def test_plan_chunks_single_chunk_when_video_is_short():
    chunks, truncated = plan_chunks(total_frames=300, fps=30.0)

    assert truncated is False
    assert len(chunks) == 1
    assert chunks[0] == ChunkPlan(
        chunk_index=0,
        frame_indices=[0, 60, 120, 180, 240],
        start_time=0.0,
        end_time=8.0,
    )


def test_plan_chunks_splits_into_multiple_chunks():
    chunks, truncated = plan_chunks(total_frames=3000, fps=30.0)

    assert truncated is False
    assert len(chunks) == 7
    assert chunks[0].frame_indices == [0, 60, 120, 180, 240, 300, 360, 420]
    assert chunks[0].start_time == 0.0
    assert chunks[0].end_time == 14.0
    assert chunks[-1].chunk_index == 6
    assert chunks[-1].frame_indices == [2880, 2940]
    assert chunks[-1].end_time == 98.0


def test_plan_chunks_truncates_long_videos():
    chunks, truncated = plan_chunks(total_frames=1_000_000, fps=30.0)

    assert truncated is True
    assert len(chunks) == 20
    assert chunks[-1].frame_indices[-1] == 9540


def test_plan_chunks_empty_video_returns_no_chunks():
    chunks, truncated = plan_chunks(total_frames=0, fps=30.0)

    assert chunks == []
    assert truncated is False


def test_plan_single_chunk_over_video_samples_evenly():
    chunk = plan_single_chunk_over_video(total_frames=179, fps=15.0, max_frames=6)

    assert chunk.frame_indices == [0, 36, 71, 107, 142, 178]
    assert chunk.start_time == 0.0
    assert chunk.end_time == pytest.approx(178 / 15)


def test_plan_single_chunk_over_video_handles_short_video():
    chunk = plan_single_chunk_over_video(total_frames=1, fps=30.0, max_frames=8)

    assert chunk.frame_indices == [0]


def test_plan_single_chunk_over_video_handles_empty_video():
    chunk = plan_single_chunk_over_video(total_frames=0, fps=30.0)

    assert chunk.frame_indices == []
