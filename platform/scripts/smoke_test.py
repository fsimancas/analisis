#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from fais.api.app import create_app
from fais.config import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a read-only FAIS API smoke test")
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    settings = replace(Settings.from_env(), database_path=args.database.resolve())
    with TestClient(create_app(settings)) as client:
        overview = client.get("/api/v1/overview")
        overview.raise_for_status()
        counts = overview.json()["counts"]
        assert counts["matches"] > 0
        matches = client.get("/api/v1/matches", params={"limit": 1})
        matches.raise_for_status()
        match_id = matches.json()[0]["id"]
        client.get(f"/api/v1/matches/{match_id}").raise_for_status()
        teams = client.get("/api/v1/teams", params={"limit": 1})
        teams.raise_for_status()
        client.get(f"/api/v1/teams/{teams.json()[0]['id']}").raise_for_status()
        client.get("/api/v1/quality/issues", params={"limit": 1}).raise_for_status()
        client.get("/api/v1/models").raise_for_status()
        client.get("/api/v1/backtests").raise_for_status()
        graphql = client.post(
            "/graphql", json={"query": "{ overview { counts { matches teams } } }"}
        )
        graphql.raise_for_status()
        assert graphql.json()["data"]["overview"]["counts"]["matches"] == counts["matches"]
        client.get("/api/v1/readiness").raise_for_status()
        metrics = client.get("/metrics")
        metrics.raise_for_status()
        assert "fais_http_requests_total" in metrics.text
    print(f"FAIS smoke test passed: {counts}")


if __name__ == "__main__":
    main()
