.PHONY: migrate import backtest predict train test lint build e2e verify

PYTHON ?= $(CURDIR)/.venv/bin/python
FAIS ?= $(CURDIR)/.venv/bin/fais
RUFF ?= $(CURDIR)/.venv/bin/ruff

migrate:
	$(FAIS) migrate

import:
	@test -n "$(SOURCE)" || (echo "Uso: make import SOURCE=../betplay_flashscore_lite.db"; exit 2)
	$(FAIS) import-legacy "$(SOURCE)"

backtest:
	$(FAIS) backtest --min-team-history 3

predict:
	@test -n "$(FROM_DATE)" || (echo "Uso: make predict FROM_DATE=2026-10-18"; exit 2)
	$(FAIS) predict-upcoming --from-date "$(FROM_DATE)" --limit 25

train:
	$(FAIS) train-xgboost --promote-if-better

test:
	cd backend && $(PYTHON) -m pytest

lint:
	cd backend && $(RUFF) check src tests
	cd web && npm run lint

build:
	cd web && npm run build

e2e:
	cd web && npm run test:e2e

verify:
	FAIS_PYTHON=$(PYTHON) FAIS_RUFF=$(RUFF) ./scripts/verify.sh
