import asyncio

import pytest

from spaceinvaders.loadtest import ClientStats, _print_report, _summary, main, run
from spaceinvaders.server import start_server


def test_summary_of_empty_list_is_none():
    assert _summary([], scale=1000) is None


def test_summary_computes_mean_p95_max():
    values = [0.01, 0.02, 0.03, 0.04, 0.05]
    result = _summary(values, scale=1000)
    assert result["n"] == 5
    assert result["mean"] == pytest.approx(30.0)
    assert result["max"] == pytest.approx(50.0)
    assert result["p95"] <= result["max"]


def test_summary_single_value():
    result = _summary([0.01], scale=1000)
    assert result["p95"] == result["max"] == pytest.approx(10.0)


def test_client_stats_records_gaps_between_snapshots():
    stats = ClientStats()
    stats.record_snapshot(100)
    assert stats.snapshot_gaps == []
    stats.record_snapshot(120)
    assert len(stats.snapshot_gaps) == 1
    assert stats.snapshot_bytes == [100, 120]


def test_run_end_to_end_reports_zero_errors():
    report = asyncio.run(run(rooms=1, players_per_room=2, duration=0.6,
                             max_players=2, host="127.0.0.1", port=0))
    assert report["connections"] == 2
    assert report["errors"] == 0
    assert report["snapshot_gap_ms"] is not None
    assert report["snapshot_gap_ms"]["mean"] > 0
    assert report["bandwidth_kb_per_s_total"] > 0


def test_run_multiple_rooms_are_independent():
    report = asyncio.run(run(rooms=2, players_per_room=1, duration=0.4,
                             max_players=1, host="127.0.0.1", port=0))
    assert report["connections"] == 2
    assert report["errors"] == 0


def test_run_client_records_error_when_room_is_full():
    async def scenario():
        server = await start_server(host="127.0.0.1", port=0, max_players=1)
        try:
            from spaceinvaders.loadtest import _run_room
            stats = await _run_room(
                f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}",
                "full-room", players=2, duration=0.3)
            return stats
        finally:
            server.close()
            await server.wait_closed()

    stats = asyncio.run(scenario())
    errors = sum(s.errors for s in stats)
    assert errors == 1


def test_run_client_records_error_on_connection_failure():
    from spaceinvaders.loadtest import _run_client

    stats = ClientStats()
    asyncio.run(_run_client("ws://127.0.0.1:1", "room", stats, 0.1, (["FIRE"],)))
    assert stats.errors == 1


def test_main_rejects_players_per_room_over_max(capsys):
    with pytest.raises(SystemExit):
        main(["--players-per-room", "6", "--max-players", "5", "--duration", "0.1"])
    captured = capsys.readouterr()
    assert "cannot exceed" in captured.err


def test_main_runs_end_to_end_and_prints_report(capsys):
    main(["--rooms", "1", "--players-per-room", "1", "--duration", "0.3", "--port", "0"])
    out = capsys.readouterr().out
    assert "Space Invaders multiplayer load test" in out
    assert "errors: 0" in out


def test_print_report_handles_missing_optional_sections(capsys):
    _print_report({
        "connections": 0, "rooms": 0, "players_per_room": 0,
        "duration_s": 1.0, "wall_s": 1.0, "errors": 0,
        "rtt_ms": None, "snapshot_gap_ms": None, "snapshot_bytes": None,
        "bandwidth_kb_per_s_total": 0.0,
    })
    out = capsys.readouterr().out
    assert "connections: 0" in out
