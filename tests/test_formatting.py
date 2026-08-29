from docker_services.formatting import human_size, short_timestamp, summarize_prune_result


def test_human_size_bytes():
    assert human_size(512) == "512 B"


def test_human_size_megabytes():
    assert human_size(5 * 1024 * 1024) == "5.0 MB"


def test_human_size_none():
    assert human_size(None) == "—"


def test_short_timestamp_trims_fractional_seconds():
    assert short_timestamp("2024-01-01T12:00:00.123456789Z") == "2024-01-01 12:00:00"


def test_short_timestamp_none():
    assert short_timestamp(None) == "—"


def test_summarize_prune_result_with_space_and_deleted():
    result = {"ImagesDeleted": [{"Deleted": "sha256:a"}, {"Deleted": "sha256:b"}], "SpaceReclaimed": 1024}
    summary = summarize_prune_result(result)
    assert "1024" not in summary
    assert "1.0 KB" in summary
    assert "2" in summary


def test_summarize_prune_result_empty():
    assert summarize_prune_result({"NetworksDeleted": None}) == "Nothing to prune."
