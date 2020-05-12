.PHONY: help

HOST:=$(shell python -c "from config import GLOBAL;print(GLOBAL['Host'])")
PORT:=$(shell python -c "from config import GLOBAL;print(GLOBAL['Port'])")

help:
	@echo " clean   remove unwanted stuff"
	@echo " test    run test examples"
	@echo " dev     start server for develpment"
	@echo " run     foreground start server for production"
	@echo " start   background start server for production"
	@echo " stop    shut down server in the background for production"
	@echo " reload  reload server in the background for production"
	@echo " restart restart server in the background for production"
	@echo " status  show server status in the background for production"

test:
	python -m unittest discover -p "test_*.py"

dev:
	export FLASK_ENV=development FLASK_APP=app.py FLASK_DEBUG=1 && flask run --host $(HOST) --port $(PORT)

run:
	sh online_gunicorn.sh run

start:
	sh online_gunicorn.sh start

stop:
	sh online_gunicorn.sh stop

reload:
	sh online_gunicorn.sh reload

restart:
	sh online_gunicorn.sh restart

status:
	sh online_gunicorn.sh status

clean:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '.DS_Store' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -rf {} +
	find . -name '.coverage' -exec rm -rf {} +
	rm -rf build dist .eggs *.egg-info +
