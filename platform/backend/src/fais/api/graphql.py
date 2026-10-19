from __future__ import annotations

from typing import Any

import strawberry
from strawberry.fastapi import GraphQLRouter

from fais.db.repositories import SportsRepository


@strawberry.type
class Competition:
    id: int
    slug: str
    name: str
    sport: str
    active: bool
    country: str | None
    match_count: int


@strawberry.type
class Match:
    id: int
    competition_id: int
    competition: str
    home_team: str
    away_team: str
    kickoff_utc: str | None
    kickoff_date: str | None
    kickoff_precision: str
    kickoff_raw: str | None
    round_name: str | None
    status: str
    home_score: int | None
    away_score: int | None


@strawberry.type
class PlatformCounts:
    countries: int
    competitions: int
    teams: int
    matches: int
    predictions: int


@strawberry.type
class Overview:
    counts: PlatformCounts
    open_quality_issues: int


def _repo(info: strawberry.Info[Any, Any]) -> SportsRepository:
    return info.context["request"].app.state.repository


@strawberry.type
class Query:
    @strawberry.field
    def overview(self, info: strawberry.Info[Any, Any]) -> Overview:
        data = _repo(info).overview()
        return Overview(
            counts=PlatformCounts(**data["counts"]), open_quality_issues=data["open_quality_issues"]
        )

    @strawberry.field
    def competitions(
        self, info: strawberry.Info[Any, Any], limit: int = 100, offset: int = 0
    ) -> list[Competition]:
        return [Competition(**row) for row in _repo(info).competitions(limit=limit, offset=offset)]

    @strawberry.field
    def matches(
        self,
        info: strawberry.Info[Any, Any],
        competition_id: int | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Match]:
        return [
            Match(**row)
            for row in _repo(info).matches(
                competition_id=competition_id, status=status, limit=limit, offset=offset
            )
        ]


schema = strawberry.Schema(query=Query)
graphql_router = GraphQLRouter(schema)
