# 安全策略

English version: [SECURITY-en.md](./SECURITY-en.md)。

## 支持范围

| 版本线 | 版本 | 是否维护 |
| --- | --- | --- |
| v2（`master`） | `2.0.0-pre` 及之后 | 是 |
| v1（`1.x` tag，`1.16.x`） | `1.16.10` 及之后 | 仅安全修复 |
| v1（`1.x` tag） | `1.16.9` 及更早 | 否，请升级到 `1.16.10` |

上报前请先在你所运行版本线的最新版上复现。

## 上报漏洞

**不要为安全问题开公开 issue、PR 或 discussion。**

按优先级选择：

1. **GitHub 私密漏洞上报**（本仓库已启用）：进入仓库页面顶部的 **Security**（标签为
   *Security and quality*），在 *Security advisories* 标题旁点击 **Report a vulnerability**。
   报告、修复与公告会留在同一个私密空间里。
   如果看不到这个按钮，请改用第 2 种方式，**不要**改开公开 issue。
2. 邮件 **me@tcw.im**，标题加前缀 `[sapic security]`。有公钥就加密，没有就先发正文，
   我们会转到私密渠道继续。

维护者注意：开关在 **Settings → Security and quality → Advanced Security → Private vulnerability
reporting**（开启时该行按钮显示 *Disable*）。**Security → Advisories → New draft security advisory**
只是发布侧：它生成 GHSA 与致谢，本身不收报告，能建草稿也不代表私密上报已开启。

请尽量写明：

- 受影响的版本 / tag / commit，以及是 v1 还是 v2；
- 你测试的部署形态（Docker 镜像、`flask run`、反代、数据库）；
- 复现步骤或 PoC，以及你认为的影响；
- 你希望在公告里使用的署名。

## 处理时限

| 阶段 | 目标 |
| --- | --- |
| 确认收到 | 3 个工作日内 |
| 初步评估（定级、受影响范围） | 10 个工作日内 |
| 发布修复或缓解措施 | 90 天内，高危更快 |
| 公开公告 | 修复版本发布后，或上报满 90 天 |

我们按 90 天协同披露执行。确实需要更多时间时，会在截止前说明并申请延期。
除明确要求匿名外，上报者会出现在公告与 `CHANGELOG.md` 里。

## 范围

纳入范围：本仓库代码（`server/` 后端、`web/` 前端、部署文件）以及由它构建的官方镜像。

不在范围：你自己部署的配置问题（例如管理员账号暴露、公网站点前没有 HTTPS、
信任不可信来源的 `X-Forwarded-*`），单独打包的第三方钩子自身的漏洞，
以及需要服务器或数据库已被攻陷才能成立的发现。

## URL 上传已有的加固

带 `url` 字段的 `POST /api/v2/upload` 会让服务端去抓取远端对象。这条路径刻意收得很窄，
下列规则都有测试覆盖（`server/tests/test_images.py`）：

- **只接受域名**：地址字面量（`http://10.0.0.1/a.png`、`https://[::1]/a.png`，公网 IP 同样）
  直接 400 —— 字面量没有可解析、可校验的东西。
- **只解析一次并绑定 IP**：域名只解析一次，逐条校验私网 / 环回 / 链路本地 / 保留 / 组播地址，
  然后把连接拨到这些地址上；域名仍用于 `Host` 头与 TLS SNI，虚拟主机与证书校验不受影响。
  不存在第二次解析（即 DNS rebinding 的 TOCTOU 缺口）。
- **不跟随重定向**：`3xx` 直接 400，不跟；跟进去就是对调用方从未指定的地址再发一次请求。
  存储后端的读取地址由 sapic 自己产生，仍保留逐跳跟随。
- **代理仅管理员可用**：配置了 `upload_fetch_proxy` 时，只有管理员的上传才会在直连失败后走代理，
  因为走代理时地址由代理解析与连接，绕过了上面所有校验。匿名与普通用户始终直连。

## 验证修复

v2 的回归测试用桩解析器确定性地模拟 DNS rebinding（第一次答公网地址、之后答内网地址），
并断言只使用第一次的结果：

```bash
cd server
python3 -m pytest tests/test_images.py -k "rebinding or redirects or address_literals or proxy" -v
```

对运行中的实例做手工验证（普通用户令牌即可）：

```bash
# 1. 地址字面量：建立连接前就被拒绝。
curl -sS -X POST https://your.site/api/v2/upload \
  -H "Authorization: Bearer $PAT" -F "url=http://127.0.0.1/secret.png"
# -> HTTP 400, {"code": "PARAM_ERROR", "message": "url host must be a domain name"}

# 2. 解析到内网地址的域名：解析后拒绝。
curl -sS -X POST https://your.site/api/v2/upload \
  -H "Authorization: Bearer $PAT" -F "url=http://internal.example.com/secret.png"
# -> HTTP 403, {"code": "FORBIDDEN", "message": "url host is not allowed"}

# 3. 返回 302 的地址：不会被跟随。
curl -sS -X POST https://your.site/api/v2/upload \
  -H "Authorization: Bearer $PAT" -F "url=http://your.site/redirect-to-internal"
# -> HTTP 400, {"code": "PARAM_ERROR", "message": "url redirects are not followed"}

# 4. DNS rebinding：搭一个实验解析器，让同一个域名第一次答公网地址（TTL 0）、第二次答内网地址。
#    修复后实例只会成功抓到公网那一次（或直接失败），内网服务收不到任何请求，
#    解析器日志里该域名只有一次查询。
```

v1 版本线的验证步骤相同，只是端点换成 `POST /api/upload`（字段 `picbed=http://…`），
修复内容见 `1.x` 安全分支及其 `CHANGELOG.md`。

## 致谢

感谢私下上报问题、帮助 sapic 变得更安全的人。经对方同意，致谢会出现在这里与
[更新日志](./CHANGELOG.md) 中：

- **Gantrel LLC (Jason Sager)** —— 上报 v1 URL 上传抓取缺少内网地址校验、v2 的校验可被 DNS rebinding
  绕过（2026-11），并审阅了修复方案。
