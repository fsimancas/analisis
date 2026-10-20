import json
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fais.api.app import create_app
from fais.auth import AuthService
from fais.config import Settings
from fais.ingestion.providers import ControlledProviderIngester


def test_controlled_details_and_odds_ingestion(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    settings = Settings(
        database_path=tmp_path / "providers.sqlite3",
        inbox_path=inbox,
        redis_url="redis://127.0.0.1:6379/15",
        cors_origins=("http://localhost:5173",),
        log_level="INFO",
        auth_secret="test-secret-that-is-not-used-in-production",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        with app.state.database.transaction() as conn:
            conn.execute("INSERT INTO countries(slug, name) VALUES ('co', 'Colombia')")
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
            conn.execute(
                """INSERT INTO scraper_sources(
                name, country_slug, competition_slug, provider_code, ingestion_kind
                ) VALUES ('FotMob details', 'co', 'league', 'fotmob', 'DETAILS')"""
            )
            conn.execute(
                """INSERT INTO scraper_sources(
                name, country_slug, competition_slug, provider_code, ingestion_kind
                ) VALUES ('BetPlay odds', 'co', 'league', 'betplay', 'ODDS')"""
            )
            payload = {
                "expected_goals": {"home": 1.5, "away": 1.0},
                "markets": {
                    "one_x_two": {"home": 0.52, "draw": 0.27, "away": 0.21},
                    "goals": {},
                    "btts": {"yes": 0.5, "no": 0.5},
                },
            }
            conn.execute(
                """INSERT INTO predictions(match_id, cutoff_utc, model_version,
                feature_version, status, home_lambda, away_lambda, payload, input_hash)
                VALUES (?, '2026-01-01T00:00:00Z', 'test-v1', 'features-v1', 'READY',
                1.5, 1.0, ?, 'provider-input')""",
                (match_id, json.dumps(payload)),
            )

        details_file = inbox / "details.json"
        details_file.write_text(
            json.dumps(
                {
                    "match_id": match_id,
                    "players": [
                        {
                            "external_id": "p1",
                            "name": "Player One",
                            "position": "GK",
                            "team_id": teams[0],
                            "shirt_number": 1,
                        },
                        {
                            "external_id": "p2",
                            "name": "Player Two",
                            "position": "FW",
                            "team_id": teams[0],
                            "shirt_number": 9,
                        },
                    ],
                    "referees": [{"external_id": "r1", "name": "Referee One", "role": "MAIN"}],
                    "lineups": [
                        {
                            "team_id": teams[0],
                            "status": "CONFIRMED",
                            "formation": "4-4-2",
                            "players": [
                                {"player_external_id": "p1", "starter": True},
                                {"player_external_id": "p2", "starter": True},
                            ],
                        }
                    ],
                    "events": [
                        {
                            "external_id": "e1",
                            "event_type": "GOAL",
                            "minute": 12,
                            "team_id": teams[0],
                            "player_external_id": "p2",
                        }
                    ],
                    "team_statistics": [{"team_id": teams[0], "key": "shots", "value": 8}],
                    "player_statistics": [
                        {
                            "player_external_id": "p2",
                            "team_id": teams[0],
                            "key": "goals",
                            "value": 1,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        ingester = ControlledProviderIngester(app.state.database, inbox)
        result = ingester.run(
            details_file,
            provider_code="fotmob",
            ingestion_kind="DETAILS",
            country_slug="co",
            competition_slug="league",
            captured_on=date(2026, 1, 1),
        )
        assert result == {
            "players": 2,
            "squads": 2,
            "referees": 1,
            "lineups": 1,
            "events": 1,
            "statistics": 1,
            "player_statistics": 1,
        }

        odds_file = inbox / "odds.json"
        odds_file.write_text(
            json.dumps(
                {
                    "odds": [
                        {
                            "match_id": match_id,
                            "market_key": "1X2",
                            "selection_key": selection,
                            "decimal_odd": odd,
                            "captured_at": "2026-01-01T10:00:00Z",
                        }
                        for selection, odd in (("HOME", 2.2), ("DRAW", 3.2), ("AWAY", 3.5))
                    ]
                }
            ),
            encoding="utf-8",
        )
        assert ingester.run(
            odds_file,
            provider_code="betplay",
            ingestion_kind="ODDS",
            country_slug="co",
            competition_slug="league",
            captured_on=date(2026, 1, 1),
        ) == {"seen": 3, "written": 3}
        ingester.run(
            odds_file,
            provider_code="betplay",
            ingestion_kind="ODDS",
            country_slug="co",
            competition_slug="league",
            captured_on=date(2026, 1, 1),
        )
        with app.state.database.connect(readonly=True) as conn:
            assert conn.execute("SELECT count(*) FROM odds_snapshots").fetchone()[0] == 3

        registered = client.post(
            "/api/v1/auth/register",
            json={
                "email": "analyst@example.com",
                "password": "correct-horse-battery-staple",
                "display_name": "Analyst",
            },
        ).json()["user"]
        with app.state.database.transaction() as conn:
            conn.execute("UPDATE users SET role='ANALYST' WHERE id=?", (registered["id"],))
        service = AuthService(app.state.database, settings)
        headers = {"Authorization": f"Bearer {service.token({**registered, 'role': 'ANALYST'})}"}
        details = client.get(f"/api/v1/matches/{match_id}/details", headers=headers)
        assert details.status_code == 200
        assert details.json()["events"][0]["event_type"] == "GOAL"
        player_ids = [item["player_id"] for item in details.json()["lineups"][0]["players"]]
        player_profile = client.get(f"/api/v1/players/{player_ids[1]}", headers=headers)
        assert player_profile.status_code == 200
        assert player_profile.json()["statistics"][0]["total"] == 1
        saved_lineup = client.put(
            f"/api/v1/matches/{match_id}/lineups",
            json={
                "team_id": teams[0],
                "status": "FINAL",
                "formation_code": "4-4-2",
                "players": [{"player_id": player_id, "starter": True} for player_id in player_ids],
            },
            headers=headers,
        )
        assert saved_lineup.status_code == 200
        value = client.get(f"/api/v1/odds/matches/{match_id}/value", headers=headers)
        assert value.status_code == 200
        assert len(value.json()["markets"]) == 3

        outside = tmp_path / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        with pytest.raises(ValueError, match="inside FAIS_INBOX_PATH"):
            ingester.run(
                outside,
                provider_code="fotmob",
                ingestion_kind="DETAILS",
                country_slug="co",
                competition_slug="league",
                captured_on=date(2026, 1, 1),
            )
