.PHONY: install format lint type unit smoke test audit check run

install:
	python -m pip install -e '.[dev]'

format:
	python -m ruff format .
	python -m ruff check --fix .

lint:
	python -m ruff format --check .
	python -m ruff check .

type:
	python -m mypy src

unit:
	python -m pytest tests/unit --cov=agent_control_plane --cov-report=term-missing

smoke:
	python -m pytest tests/smoke -m smoke

test:
	python -m pytest --cov=agent_control_plane --cov-report=term-missing

audit:
	python -m pip_audit

check: lint type test

run:
	python -m agent_control_plane
