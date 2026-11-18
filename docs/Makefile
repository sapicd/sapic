# sapic 文档构建
#
#   make html        生成中文 HTML 到 _build/html
#   make html-en     生成英文 HTML 到 _build/html/en（用 locale/en 的译文）
#   make gettext     抽取待译条目到 _build/gettext/*.pot
#   make update-po   抽取并同步 locale/en 下的 .po（新增/变动条目会标出来）
#   make linkcheck   检查外链（可选）
#   make clean       清理构建产物
#
# 依赖：pip install -r docs/requirements.txt（或仓库根的 make docs）

# 优先用仓库根的虚拟环境，其次用 PATH 里的 python3
PYTHON ?= $(shell [ -x ../.venv/bin/python ] && echo ../.venv/bin/python || echo python3)
SPHINXBUILD ?= $(PYTHON) -m sphinx
SPHINXINTL ?= $(PYTHON) -m sphinx_intl
SOURCEDIR = .
BUILDDIR = _build

.PHONY: help html html-en gettext update-po linkcheck clean

help:
	@echo "make html       构建中文 HTML 文档"
	@echo "make html-en    构建英文 HTML（-D language=en）"
	@echo "make gettext    抽取待译条目到 $(BUILDDIR)/gettext"
	@echo "make update-po  抽取并同步 locale/en 的 .po"
	@echo "make linkcheck  检查文档里的外部链接"
	@echo "make clean      清理 $(BUILDDIR)"

html:
	$(SPHINXBUILD) -b html -W --keep-going "$(SOURCEDIR)" "$(BUILDDIR)/html"
	@echo "构建完成：$(BUILDDIR)/html/index.html"

html-en:
	$(SPHINXBUILD) -b html -D language=en -W --keep-going "$(SOURCEDIR)" "$(BUILDDIR)/html/en"
	@echo "构建完成：$(BUILDDIR)/html/en/index.html"

gettext:
	$(SPHINXBUILD) -b gettext "$(SOURCEDIR)" "$(BUILDDIR)/gettext"

update-po: gettext
	$(SPHINXINTL) update -p "$(BUILDDIR)/gettext" -l en -d locale

linkcheck:
	$(SPHINXBUILD) -b linkcheck "$(SOURCEDIR)" "$(BUILDDIR)/linkcheck"

clean:
	rm -rf "$(BUILDDIR)"
