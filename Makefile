.PHONY: setup-python-dev test test-knowledge test-research test-web type-check type-check-docker build-web config compose-config

setup-python-dev:
	bash scripts/setup_python_dev.sh

test:
	bash scripts/test_all.sh

test-knowledge:
	services/knowledge/.venv/bin/python -m pytest -c services/knowledge/pytest.ini services/knowledge/tests

test-research:
	services/research/.venv/bin/python -m pytest -c services/research/pytest.ini services/research/tests

test-web:
	pnpm --dir apps/web test

type-check:
	bash scripts/check_python_types.sh

type-check-docker:
	bash scripts/check_python_types_docker.sh

build-web:
	pnpm --dir apps/web run build

compose-config:
	docker compose config --quiet
