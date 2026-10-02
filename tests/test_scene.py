from unittest.mock import patch

from visualintel.cli import main


def test_scene_samples_requested_instant_only(tiny_video, capsys):
    with patch("visualintel.cli.check_ollama_ready"), patch(
        "visualintel.engine.call_model", return_value='{"answer":"A room with a person and a cup."}'
    ) as model:
        assert main(["scene", tiny_video, "--at", "0"]) == 0
    args, kwargs = model.call_args
    assert len(args[0]) == 1
    assert kwargs["generation_options"]["num_predict"] == 96
    output = capsys.readouterr().out
    assert "0.00s" in output
    assert "A room with a person and a cup." in output


def test_scene_rejects_invalid_time_before_model(tiny_video, capsys):
    for value in ("-1", "nan", "inf", "999999"):
        with patch("visualintel.cli.check_ollama_ready") as ready:
            assert main(["scene", tiny_video, "--at", value]) == 1
            ready.assert_not_called()
        assert "--at" in capsys.readouterr().err
