# sapic 文档构建
#
#   make html        生成 HTML 到 _build/html
#   make linkcheck   检查外链（可选）
#   make clean       清理构建产物
#
# 依赖：pip install -r docs/requirements.txt（或仓库根的 make docs）

# 优先用仓库根的虚拟环境，其次用 PATH 里的 python3
PYTHON ?= $(shell [ -x ../.venv/bin/python ] && echo ../.venv/bin/python || echo python3)
SPHINXBUILD ?= $(PYTHON) -m sphinx
SOURCEDIR = .
BUILDDIR = _build

.PHONY: help html linkcheck clean

help:
	@echo "make html       构建 HTML 文档"
	@echo "make linkcheck  检查文档里的外部链接"
	@echo "make clean      清理 $(BUILDDIR)"

html:
	$(SPHINXBUILD) -b html -W --keep-going "$(SOURCEDIR)" "$(BUILDDIR)/html"
	@echo "构建完成：$(BUILDDIR)/html/index.html"

linkcheck:
	$(SPHINXBUILD) -b linkcheck "$(SOURCEDIR)" "$(BUILDDIR)/linkcheck"

clean:
	rm -rf "$(BUILDDIR)"
