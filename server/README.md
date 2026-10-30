# sapic server (v2)

sapic v2 后端，API-only（前端由独立的 Vue 应用提供）。

## 运行要求

- Python 3.10+
- PostgreSQL（推荐）或 MySQL 8
- Redis（会话、限流、异步任务）

## 依赖安装

```bash
cd server
python -m pip install -e ".[dev]"
```

## 配置

配置读取顺序：默认值 → `server/.cfg`（`key=value`）→ 环境变量（`sapic_` 前缀）。

| 配置项 | 说明 | 默认值 |
| --- | --- | --- |
| `sapic_db_url` | 数据库 DSN，如 `postgresql://user:pass@host:5432/sapic`、`mysql://...`、`sqlite:///tmp/sapic.db` | 空（必填） |
| `sapic_redis_url` | Redis DSN，如 `redis://:pass@host:6379/0` | 空（可选） |
| `sapic_secretkey` | Web 应用密钥 | 内置串 |
| `sapic_maxupload` | 上传上限，单位 MB | `20` |
| `sapic_storagedir` | 本地存储目录 | `data/upload` |
| `sapic_external_base_url` | 对外访问根地址，用于拼接图片外链 | 空（相对地址） |
| `sapic_proxyfix` | 是否信任代理标头 | 关闭 |
| `sapic_hookreloadtime` | 钩子重载间隔，单位秒 | `600` |

## 数据库初始化

```bash
cd server
export FLASK_APP=sapic
flask sa upgrade          # 建表 / 增量迁移
flask sa create-admin -u admin -p 123456
```

## 启动

```bash
cd server
flask run --host 0.0.0.0 --port 9514
```

生产环境使用 gunicorn：

```bash
gunicorn "sapic:create_app()" -b 0.0.0.0:9514 -w 4 -k gevent
```

## API 概览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/health` | 健康检查（DB / Redis） |
| POST | `/api/v1/auth/register` | 注册 |
| POST | `/api/v1/auth/login` | 登录（Cookie 会话，返回 CSRF） |
| POST | `/api/v1/auth/logout` | 登出 |
| GET | `/api/v1/auth/session` | 当前会话 |
| POST | `/api/v1/auth/password/forgot` | 发送重置令牌（10 分钟） |
| POST | `/api/v1/auth/password/reset` | 使用令牌重置密码 |
| PUT | `/api/v1/auth/password` | 修改密码（吊销其它会话） |
| GET/POST | `/api/v1/auth/tokens` | 列出 / 创建 PAT |
| DELETE | `/api/v1/auth/tokens/<id>` | 撤销 PAT |
| POST | `/api/v1/uploads` | 上传（multipart，字段 `file`） |
| GET | `/api/v1/images` | 图片列表（游标分页，权限过滤） |
| GET/PATCH/DELETE | `/api/v1/images/<sha>` | 详情 / 修改 / 删除 |
| GET/POST | `/api/v1/albums` | 相册列表 / 创建 |
| PATCH/DELETE | `/api/v1/albums/<id>` | 修改 / 删除（非空拒绝） |
| GET | `/i/<sha>` | 图片读取（优先级选择副本，支持 Range） |
| POST | `/api/upload` | v1 兼容上传（`picbed` + `token`） |
| GET/PUT/DELETE | `/api/sha/<sha>` | v1 兼容图片管理 |

认证方式：Cookie 会话（写操作需要 `X-CSRF-Token`）或 `Authorization: Bearer <PAT>`；v1 兼容接口额外接受 `token` 参数。

## 当前实现范围

- 已完成：应用工厂、Peewee 模型、迁移框架、健康检查、注册/登录/找回密码/PAT、上传与读取、相册权限、存储后端优先级、v1 兼容接口。
- 待实现：用户自定义存储后端管理 API、上传票据（Upload Ticket）、多副本异步复制与对账、相册共享成员管理、管理后台 API、第三方插件安装持久化、OIDC 对接。

## 测试

```bash
cd server
python -m pytest -q
```

测试默认使用临时 SQLite 数据库；CI 建议增加 PostgreSQL / MySQL 双库矩阵。
