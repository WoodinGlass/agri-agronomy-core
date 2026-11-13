.PHONY: install install-dev lock lint format typecheck test coverage perf check precommit audit build smoke clean wheel-prep cargo-check rust-test rust-lint

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"
	pre-commit install

lock:
	pip-compile --generate-hashes --allow-unsafe --extra dev pyproject.toml -o requirements.lock

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

typecheck:
	mypy

test:
	pytest -m "not perf"

coverage:
	pytest -m "not perf"
	coverage report --fail-under=90 --skip-covered

check: lint typecheck coverage

perf:
	pytest -m perf --no-cov -q

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
	.smoke-venv/bin/agri-core validate --pack sample

clean:
	rm -rf build dist .smoke-venv .pytest_cache .ruff_cache .mypy_cache .hypothesis

wheel-prep:
	mkdir -p src/agri_core/_data
	rm -rf src/agri_core/_data/schema src/agri_core/_dictionary
	cp -R schema src/agri_core/_data/schema
	cp -R dictionary src/agri_core/_dictionary

cargo-check:
	cargo fmt --all -- --check
	cargo clippy --all-targets -- -D warnings
	cargo test --locked
	cargo deny check

rust-test:
	cargo test --locked

rust-lint:
	cargo fmt --all -- --check
	cargo clippy --all-targets -- -D warnings
