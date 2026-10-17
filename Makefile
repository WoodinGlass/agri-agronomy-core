.PHONY: install install-dev lint format typecheck test check precommit audit build smoke clean

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"
	pre-commit install

lock:
	pip-compile --generate-hashes --extra dev pyproject.toml -o requirements.lock

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

typecheck:
	mypy

test:
	pytest

check: lint typecheck test

precommit:
	pre-commit run --all-files

audit:
	pip-audit --skip-editable

build:
	python -m build

smoke: build
	python -m venv .smoke-venv
	.smoke-venv/bin/pip install --upgrade pip
	.smoke-venv/bin/pip install dist/*.whl
	.smoke-venv/bin/python -c "import agri_core; print(agri_core.__version__)"

clean:
	rm -rf build dist .smoke-venv .pytest_cache .ruff_cache .mypy_cache .hypothesis
