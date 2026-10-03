import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_scene_latency.py"
spec = importlib.util.spec_from_file_location("benchmark_scene_latency", SCRIPT)
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def test_split_rounds_even_and_uneven():
    assert bench.split_rounds(list(range(12)), 3) == [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9, 10, 11]]
    assert [len(g) for g in bench.split_rounds(list(range(13)), 3)] == [5, 4, 4]
    assert sum(bench.split_rounds(list(range(13)), 3), []) == list(range(13))


def test_condition_order_is_a_latin_square():
    sides = [640, 480, 320]
    orders = [bench.condition_order(r, sides) for r in range(3)]
    assert orders[0] == [640, 480, 320]
    for position in range(3):
        assert sorted(order[position] for order in orders) == sorted(sides)


def test_evenly_spaced_indices_cover_endpoints():
    indices = bench.evenly_spaced_indices(179, 13)
    assert indices[0] == 0 and indices[-1] == 178
    assert len(set(indices)) == 13
    assert indices == sorted(indices)


def test_summarize_reports_median_range_and_iqr():
    stats = bench.summarize([1.0, 2.0, 3.0, 4.0, 5.0])
    assert stats == {"n": 5, "median": 3.0, "min": 1.0, "max": 5.0, "iqr": 2.0}
    assert bench.summarize([]) == {"n": 0}
    assert "iqr" not in bench.summarize([2.5])
