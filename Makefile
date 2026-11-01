# sapic v2 — 常用命令入口
#
# 约定：
#   - 后端在 server/，包名 sapic（本地包，不发布 PyPI、也不安装；依赖走 requirements/）
#   - 命令均在 server/ 下执行，cwd 已在 sys.path，直接 import sapic，无需 pip install
#   - 前端在 web/，独立 pnpm 工程（make 会自动检测/安装 pnpm）
#   - 变量可在命令行覆盖，如 make dev PORT=8080

PY ?= $(shell [ -x $(CURDIR)/.venv/bin/python ] && echo $(CURDIR)/.venv/bin/python || echo python3)
PNPM ?= pnpm
PNPM_VERSION ?= 8.14.1
SERVER_DIR ?= server
FLASK_APP ?= sapic
HOST ?= 0.0.0.0
PORT ?= 9514
WORKERS ?= 4
U ?= admin
P ?=

export FLASK_APP

.DEFAULT_GOAL := help
.PHONY: help setup install-prod config upgrade create-admin test dev serve \
	web-dev web-build clean ensure-pnpm

help:
	@echo "安装"
	@echo "  setup          安装开发依赖（后端 dev.txt + 前端 pnpm install）"
	@echo "  install-prod   安装生产部署依赖 (requirements/prod.txt)"
	@echo ""
	@echo "后端（均在 $(SERVER_DIR)/ 下执行，本地包无需安装）"
	@echo "  dev            启动开发服务器 (HOST=$(HOST) PORT=$(PORT)，改代码自动重载)"
	@echo "  serve          gunicorn 前台运行 (WORKERS=$(WORKERS) -k gevent)"
	@echo "  config         打印当前生效配置"
	@echo "  upgrade        建表 / 增量迁移"
	@echo "  create-admin   创建管理员 (U=$(U) P=密码)"
	@echo "  test           运行后端测试 (pytest)"
	@echo ""
	@echo "前端"
	@echo "  web-dev        启动 Vite 开发服务器 (127.0.0.1:5173)"
	@echo "  web-build      构建到 web/dist"
	@echo ""
	@echo "清理"
	@echo "  clean          清理缓存与构建产物"

setup: ensure-pnpm
	$(PY) -m pip install -r requirements/dev.txt
	cd web && $(PNPM) install

install-prod:
	$(PY) -m pip install -r requirements/prod.txt

# 确保 pnpm 可用：优先 corepack，失败再回退到 npm 全局安装
ensure-pnpm:
	@command -v $(PNPM) >/dev/null 2>&1 || { \
		echo ">> 未检测到 pnpm，尝试自动安装 pnpm@$(PNPM_VERSION)..."; \
		(corepack enable >/dev/null 2>&1 && corepack prepare pnpm@$(PNPM_VERSION) --activate) \
		|| npm install -g pnpm@$(PNPM_VERSION); \
	}

config:
	cd $(SERVER_DIR) && $(PY) -c "import json; from sapic.basis.conf import load_config; print(json.dumps(load_config(), indent=2, ensure_ascii=False))"

upgrade:
	cd $(SERVER_DIR) && $(PY) -m flask sa upgrade

create-admin:
	@test -n "$(P)" || (echo "用法: make create-admin U=$(U) P='你的密码'"; exit 1)
	cd $(SERVER_DIR) && $(PY) -m flask sa create-admin -u $(U) -p "$(P)"

test:
	cd $(SERVER_DIR) && $(PY) -m pytest -q

# --reload：改后端代码自动重启（不启用交互式调试器，避免监听 0.0.0.0 时暴露）
dev:
	cd $(SERVER_DIR) && $(PY) -m flask run --host $(HOST) --port $(PORT) --reload

serve:
	cd $(SERVER_DIR) && $(PY) -m gunicorn "sapic:create_app()" -b $(HOST):$(PORT) -w $(WORKERS) -k gevent

web-dev: ensure-pnpm
	cd web && $(PNPM) run dev

web-build: ensure-pnpm
	cd web && $(PNPM) run build

clean:
	rm -rf .pytest_cache web/dist
	find $(SERVER_DIR)/sapic $(SERVER_DIR)/tests -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
	find $(SERVER_DIR)/sapic $(SERVER_DIR)/tests -name '*.py[co]' -delete 2>/dev/null || true
