.PHONY: help

HOST:=$(shell python -c "from config import GLOBAL;print(GLOBAL['Host'])")
PORT:=$(shell python -c "from config import GLOBAL;print(GLOBAL['Port'])")

help:
	@echo " clean   remove unwanted stuff"
	@echo " test    run test examples"
	@echo " run     start a server for develpment"

test:
	python -m unittest discover -p "test_*.py"

run:
	export FLASK_ENV=development FLASK_APP=app.py FLASK_DEBUG=1 FLASK_SKIP_DOTENV=1 PIPENV_DONT_LOAD_ENV=1 && flask run --host $(HOST) --port $(PORT)

clean:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '.DS_Store' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -rf {} +
	find . -name '.coverage' -exec rm -rf {} +
	rm -rf build dist .eggs *.egg-info +
