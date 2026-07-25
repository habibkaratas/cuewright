.PHONY: help install test lint fmt check build clean

help:
	@echo "install  install the package with dev dependencies (editable)"
	@echo "test     run the test suite"
	@echo "lint     ruff check + format check"
	@echo "fmt      apply ruff formatting and safe fixes"
	@echo "check    lint and test, what CI runs"
	@echo "build    build sdist and wheel"
	@echo "clean    remove build and cache artefacts"

install:
	pip install -e ".[dev]"

test:
	pytest -q

lint:
	ruff check .
	ruff format --check .

fmt:
	ruff check --fix .
	ruff format .

check: lint test

build:
	python -m build

clean:
	rm -rf build dist *.egg-info src/*.egg-info .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
