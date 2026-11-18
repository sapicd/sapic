# 从 v1 迁移数据

v1 的数据在 Redis 里（`picbed:*` 键），文件在你那台 v1 部署的 `src/static/upload` 目录下
（v1 代码已从本仓库移除，看旧版本用 git tag）。`tools/migrate_v1_to_v2.py` 把它们写进 v2 的
关系库与存储后端。

只迁数据、不含 v2 自身的升级流程：拉代码 → 装依赖 → 重建前端 → 重启，见[部署与运维](deploy.md)。

## 基本用法

```bash
# dry run first: nothing is written
./.venv/bin/python tools/migrate_v1_to_v2.py --dry-run \
    --redis-url redis://127.0.0.1:6379/0 \
    --v1-upload-dir /srv/sapic-v1/src/static/upload

# real run (reads DATABASE_URL / STORAGE_DIR from server/.cfg by default)
./.venv/bin/python tools/migrate_v1_to_v2.py \
    --redis-url redis://127.0.0.1:6379/0 \
    --v1-upload-dir /srv/sapic-v1/src/static/upload
```

v1 只用云存储（又拍云 / 七牛）时**没有本地目录，直接省略 `--v1-upload-dir`**：图片从 bucket
采纳、字节确实丢了的登记成外链，**不会**被跳过——`--skip-images` 是「只迁用户与相册」，
两者不是一回事。

用镜像部署时可以不开宿主机环境，直接在容器里跑（`tools/` 已打进镜像，工作目录就是 `/app`；
`redis-py` 不在运行时依赖里，临时装一次即可）：

```bash
docker compose run --rm --entrypoint sh sapic -c \
  'pip install -q redis && python /app/tools/migrate_v1_to_v2.py --dry-run \
     --redis-url redis://v1-redis:6379/0 --v1-upload-dir /v1-upload'
```

`--v1-upload-dir` 指向 v1 的目录，需要 `-v /srv/sapic-v1/src/static/upload:/v1-upload:ro`
把它挂进来；库与 `STORAGE_DIR` 走 compose 里的环境变量与数据卷。

## 行为与规则

- **幂等**：用户按 `username`、相册按 `(owner, name)`、图片按 `sha` 去重，中断后直接重跑，只补缺的部分。
- **sha 不变**：迁移保留 v1 的 `sha`，已发布的 `/raw/<sha>` 与直链继续有效。
- **文件走存储驱动**：原文件重新写进当前主后端（默认 `up2local` 的 `STORAGE_DIR`），不是简单搬目录；
  文件已丢失的图片会登记为外链（`source_url` 指向 v1 的 `src`），不会被丢弃。
- **v1 存在云存储（又拍云/七牛）时不会变成外链**：只要图片的 `src` 就在主后端的公开域名下，
  脚本直接把 bucket 里已有的对象登记成 `ok` 副本（`images_adopted`），不下载、不重传，
  删除时也会真正删掉对象；v1 的域名和现在配的不一样时，用 `--v1-src-prefix https://旧域名`
  告诉脚本按哪个前缀还原对象路径。
- **已经按旧版本迁过一遍、图片都成了外链**：不用清库重来——确认后端配好加速域名后，
  带着 `--refresh-external` 再跑一次，会把 `source_url` 的外链行就地补成 `ok` 副本（`images_adopted`）。
- **大小 / 类型 / 尺寸不再未知**：v1 把上传时的存储返回存在 `senders` 里（字节数在 `file-size`，
  有些版本只记 HTTP 的 `content-length`；另有 `width`/`height`/`content-md5`），脚本据此填
  `size`/`mime`/`width`/`height` 和副本 `etag`；早期跑出来 `0 B / 未知类型 / 未知` 的行，
  用 `--refresh-external` 重跑即可补齐（不需要重新上传）。
- **可见性**：v1 没有可见性概念、图片都是免登录直链，所以迁移出的相册与图片默认 `public`；
  需要收紧用 `--visibility private`（会同时改相册与图片，老直链随即失效）。
- 其余参数：`--only-user alice`、`--limit 100`、`--v2-db-url`、`--v2-storage-dir`；
  `--skip-images`（只迁用户与相册）、`--skip-users`（只迁图片）。
- **依赖**：数据库驱动复用应用依赖——PostgreSQL 走 `psycopg`（v3）、MySQL 走 `PyMySQL`，都在
  `server/requirements/base.txt` 里；工具没有单独的 requirements 文件，直接用仓库 `.venv` 运行。
- **redis-py 要单独装**：v2 应用不再依赖 Redis，只有这个工具要读 v1 的 `picbed:*` 键，
  现装的虚拟环境里没有就先 `pip install redis`（`server/requirements/dev.txt` 里有）。
- `--redis-url` 必填，`--v2-db-url` 省略时才用配置里的 `DATABASE_URL`。
- 有失败项时退出码为 `1`，清单里给出 sha 与原因；修复后重跑即可。
- 迁移前先停 v1 写入（或只读挂载 Redis），避免迁移期间新增图片没有进入快照。

## 客户端要改一次配置

v1 的 `POST /api/upload` 兼容端点已移除，上传统一为 `POST /api/v2/upload` + 访问令牌（PAT）。
PicGo / uPic / Typora / 右键菜单 / 油猴脚本的逐项配置见[快捷上传](usage.md)。
