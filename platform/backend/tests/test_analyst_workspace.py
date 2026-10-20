import json
from pathlib import Path

from fastapi.testclient import TestClient

from fais.analytics.montecarlo import MonteCarloConfig, MonteCarloSimulator
from fais.analytics.odds_analysis import analyze_odds
from fais.api.app import create_app
from fais.auth import AuthService
from fais.config import Settings


def test_monte_carlo_is_reproducible_and_odds_have_expected_value() -> None:
    config = MonteCarloConfig(iterations=5_000, seed=77)
    first = MonteCarloSimulator.run(1.6, 1.1, config)
    second = MonteCarloSimulator.run(1.6, 1.1, config)
    assert first == second
    assert abs(sum(first["one_x_two"].values()) - 1) < 1e-12
    assert 0 <= first["markets"]["btts_yes"] <= 1
    analyzed = analyze_odds(
        [
            {
                "id": 1,
                "provider_id": 1,
                "market_key": "1X2",
                "selection_key": "HOME",
                "line": None,
                "captured_at": "2026-01-01",
                "decimal_odd": 2.5,
            },
            {
                "id": 2,
                "provider_id": 1,
                "market_key": "1X2",
                "selection_key": "DRAW",
                "line": None,
                "captured_at": "2026-01-01",
                "decimal_odd": 3.2,
            },
            {
                "id": 3,
                "provider_id": 1,
                "market_key": "1X2",
                "selection_key": "AWAY",
                "line": None,
                "captured_at": "2026-01-01",
                "decimal_odd": 3.0,
            },
        ],
        {"markets": {"one_x_two": {"home": 0.5, "draw": 0.25, "away": 0.25}}},
    )
    assert analyzed[0]["selection_key"] == "HOME"
    assert analyzed[0]["expected_value"] == 0.25


def test_analyst_can_run_and_persist_simulation(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "analyst.sqlite3",
        redis_url="redis://127.0.0.1:6379/15",
        cors_origins=("http://localhost:5173",),
        log_level="INFO",
        auth_secret="test-secret-that-is-not-used-in-production",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        with app.state.database.transaction() as conn:
            conn.execute("INSERT INTO countries(slug, name) VALUES ('test', 'Test')")
            country = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute(
                "INSERT INTO competitions(country_id, slug, name) VALUES (?, 'league', 'League')",
                (country,),
            )
            competition = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            for name in ("Alpha", "Beta"):
                conn.execute(
                    """INSERT INTO teams(canonical_name, normalized_name, country_id)
                    VALUES (?, ?, ?)""",
                    (name, name.casefold(), country),
                )
            teams = [row[0] for row in conn.execute("SELECT id FROM teams ORDER BY id")]
            conn.execute(
                """INSERT INTO matches(competition_id, home_team_id, away_team_id,
                status, match_type) VALUES (?, ?, ?, 'SCHEDULED', 'UPCOMING')""",
                (competition, *teams),
            )
            match_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            payload = {
                "expected_goals": {"home": 1.4, "away": 0.9},
                "markets": {
                    "one_x_two": {"home": 0.5, "draw": 0.28, "away": 0.22},
                    "goals": {"over_2.5": 0.48, "under_2.5": 0.52},
                    "btts": {"yes": 0.45, "no": 0.55},
                },
            }
            conn.execute(
                """INSERT INTO predictions(match_id, cutoff_utc, model_version,
                feature_version, status, home_lambda, away_lambda, payload, input_hash)
                VALUES (?, '2026-01-01T00:00:00Z', 'test-v1', 'test-features',
                'READY', 1.4, 0.9, ?, 'input-hash')""",
                (match_id, json.dumps(payload)),
            )
        registration = client.post(
            "/api/v1/auth/register",
            json={
                "email": "analyst@example.com",
                "password": "correct-horse-battery-staple",
                "display_name": "Analyst",
            },
        ).json()
        user = registration["user"]
        with app.state.database.transaction() as conn:
            conn.execute("UPDATE users SET role='ANALYST' WHERE id=?", (user["id"],))
        service = AuthService(app.state.database, settings)
        headers = {"Authorization": f"Bearer {service.token({**user, 'role': 'ANALYST'})}"}
        simulation = client.post(
            f"/api/v1/analyst/workspace/montecarlo/{match_id}",
            json={"iterations": 2_000, "seed": 12},
            headers=headers,
        )
        assert simulation.status_code == 200
        assert simulation.json()["result"]["iterations"] == 2_000
        runs = client.get("/api/v1/analyst/workspace/runs", headers=headers).json()
        assert len(runs) == 1
        assert runs[0]["status"] == "SUCCEEDED"
