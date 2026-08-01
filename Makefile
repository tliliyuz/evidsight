.PHONY: test test-knowledge test-research test-web build-web config compose-config

test:
	bash scripts/test_all.sh

test-knowledge:
	services/knowledge/.venv/bin/python -m pytest -c services/knowledge/pytest.ini services/knowledge/tests

test-research:
	services/research/.venv/bin/python -m pytest -c services/research/pytest.ini services/research/tests

test-web:
	npm --prefix apps/web test

build-web:
	npm --prefix apps/web run build

compose-config:
	docker compose config --quiet
