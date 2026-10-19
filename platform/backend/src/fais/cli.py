from __future__ import annotations

import argparse
import getpass
import json
import os
from dataclasses import asdict
from datetime import date
from pathlib import Path

from fais.analytics import PredictionEngine, WalkForwardBacktest
from fais.analytics.ml import XGBoostTrainer
from fais.auth import AuthService
from fais.config import Settings
from fais.db import Database
from fais.db.migrate import migrate
from fais.ingestion import LegacyImporter
from fais.ingestion.inbox import InboxScanner
from fais.ingestion.json_feed import JsonMatchFeed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fais")
    parser.add_argument("--database", type=Path, help="Override canonical SQLite path")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser(
        "check-config", help="Validate deployment configuration without exposing secrets"
    )
    sub.add_parser("migrate", help="Apply canonical schema migrations")
    importer = sub.add_parser("import-legacy", help="Import the legacy SQLite snapshot")
    importer.add_argument("source", type=Path)
    importer.add_argument(
        "--reference-date",
        type=date.fromisoformat,
        help="Capture date used to recover years omitted by Flashscore (YYYY-MM-DD)",
    )
    importer.add_argument("--source-timezone", default="America/Bogota")
    feed = sub.add_parser("ingest-json", help="Ingest a JSON snapshot emitted by a scraper")
    feed.add_argument("source", type=Path)
    feed.add_argument("--country", required=True, help="Canonical country slug")
    feed.add_argument("--competition", required=True, help="Canonical competition slug")
    feed.add_argument("--captured-on", required=True, type=date.fromisoformat)
    feed.add_argument("--source-timezone", default="America/Bogota")
    scanner = sub.add_parser("scan-inbox", help="Import changed country/competition JSON feeds")
    scanner.add_argument("--path", type=Path, help="Override FAIS_INBOX_PATH")
    bootstrap = sub.add_parser("bootstrap-admin", help="Create or promote an administrator")
    bootstrap.add_argument("--email", required=True)
    bootstrap.add_argument("--display-name", default="FAIS Administrator")
    sub.add_parser("stats", help="Show canonical database counts")
    backtest = sub.add_parser("backtest", help="Run a strict chronological model evaluation")
    backtest.add_argument("--min-team-history", type=int, default=3)
    backtest.add_argument("--limit", type=int)
    predict = sub.add_parser("predict-upcoming", help="Generate predictions for upcoming matches")
    predict.add_argument("--from-date", type=date.fromisoformat, required=True)
    predict.add_argument("--limit", type=int, default=25)
    train = sub.add_parser("train-xgboost", help="Train and register a chronological CPU model")
    train.add_argument("--artifact-dir", type=Path)
    train.add_argument("--min-team-history", type=int, default=3)
    train.add_argument("--limit", type=int)
    train.add_argument("--minimum-test-matches", type=int, default=500)
    train.add_argument("--promote-if-better", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = Settings.from_env()
    if args.command == "check-config":
        issues = settings.production_issues()
        result = {"valid": not issues, "environment": settings.environment, "issues": issues}
        print(json.dumps(result, indent=2))
        if issues:
            raise SystemExit(2)
        return
    database = Database(args.database or settings.database_path)
    if args.command == "migrate":
        print(json.dumps({"applied": migrate(database)}, indent=2))
    elif args.command == "bootstrap-admin":
        migrate(database)
        password = os.getenv("FAIS_ADMIN_PASSWORD") or getpass.getpass("Administrator password: ")
        user = AuthService(database, settings).bootstrap_admin(
            args.email, password, args.display_name
        )
        print(json.dumps({"id": user["id"], "email": user["email"], "role": user["role"]}))
    elif args.command == "import-legacy":
        migrate(database)
        print(
            json.dumps(
                asdict(
                    LegacyImporter(
                        database,
                        reference_date=args.reference_date,
                        source_timezone=args.source_timezone,
                    ).run(args.source)
                ),
                indent=2,
            )
        )
    elif args.command == "stats":
        with database.connect(readonly=True) as conn:
            tables = ("countries", "competitions", "teams", "matches", "predictions")
            print(
                json.dumps(
                    {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in tables},
                    indent=2,
                )
            )
    elif args.command == "ingest-json":
        migrate(database)
        print(
            json.dumps(
                asdict(
                    JsonMatchFeed(database).run(
                        args.source,
                        country_slug=args.country,
                        competition_slug=args.competition,
                        captured_on=args.captured_on,
                        source_timezone=args.source_timezone,
                    )
                ),
                indent=2,
            )
        )
    elif args.command == "scan-inbox":
        migrate(database)
        result = InboxScanner(database, args.path or settings.inbox_path).scan()
        print(json.dumps(asdict(result), indent=2))
    elif args.command == "backtest":
        migrate(database)
        print(
            json.dumps(
                WalkForwardBacktest(database).run(
                    min_team_history=max(args.min_team_history, 0), limit=args.limit
                ),
                indent=2,
            )
        )
    elif args.command == "predict-upcoming":
        migrate(database)
        with database.connect(readonly=True) as conn:
            match_ids = [
                row[0]
                for row in conn.execute(
                    """
                    SELECT id FROM matches
                    WHERE status='SCHEDULED' AND kickoff_date>=?
                    ORDER BY COALESCE(kickoff_utc, kickoff_date || 'T00:00:00Z'), id
                    LIMIT ?
                    """,
                    (args.from_date.isoformat(), min(max(args.limit, 1), 1000)),
                )
            ]
        engine = PredictionEngine(database)
        completed = []
        failed = []
        for match_id in match_ids:
            try:
                engine.predict(match_id)
                completed.append(match_id)
            except Exception as error:
                failed.append({"match_id": match_id, "error": str(error)})
        print(json.dumps({"predicted": completed, "failed": failed}, indent=2))
    elif args.command == "train-xgboost":
        migrate(database)
        artifact_dir = args.artifact_dir or database.path.parent / "models"
        result = XGBoostTrainer(database, artifact_dir).run(
            min_team_history=max(args.min_team_history, 0),
            limit=args.limit,
            promote_if_better=args.promote_if_better,
            minimum_matches=max(args.minimum_test_matches, 1),
        )
        print(json.dumps(asdict(result), indent=2))


if __name__ == "__main__":
    main()
