.PHONY: install dev lint format test run docker cli-help

install:
	python -m pip install -r requirements.txt

dev:
	python -m pip install -r requirements-dev.txt

lint:
	ruff check .
	ruff format --check .

format:
	ruff format .
	ruff check --fix .

test:
	pytest

run:
	uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

cli-help:
	python -m app.cli --help

docker:
	docker compose up --build
