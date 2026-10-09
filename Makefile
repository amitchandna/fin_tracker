# Fin Tracker developer commands. Override DATA to point at your CSV folder:
#   make run DATA=~/Documents/bank-exports
DATA ?= $(CURDIR)/data
PY ?= python3
VENV := backend/.venv
BIN := $(VENV)/bin

.PHONY: install build run demo dev-backend dev-frontend test sample-data clean

install:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -q -r backend/requirements-dev.txt
	cd frontend && npm install

build:
	cd frontend && npm run build

# Production-style: one server on http://localhost:8000 serving API + built UI.
run: build
	cd backend && FIN_TRACKER_DATA_DIR=$(abspath $(DATA)) .venv/bin/uvicorn app.main:app --port 8000

# Same, using the bundled sample exports.
demo:
	$(MAKE) run DATA=$(CURDIR)/sample_data

# Development: run these two in separate terminals, then open http://localhost:5173
dev-backend:
	cd backend && FIN_TRACKER_DATA_DIR=$(abspath $(DATA)) .venv/bin/uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

test:
	cd backend && .venv/bin/pytest -q
	cd frontend && npm run typecheck && npm test

sample-data:
	$(PY) scripts/generate_sample_data.py

clean:
	rm -rf frontend/dist sample_data/.fintracker
