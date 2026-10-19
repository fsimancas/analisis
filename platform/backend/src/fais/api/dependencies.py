from fastapi import Request

from fais.db import Database
from fais.db.repositories import SportsRepository


def get_repository(request: Request) -> SportsRepository:
    return request.app.state.repository


def get_database(request: Request) -> Database:
    return request.app.state.database
