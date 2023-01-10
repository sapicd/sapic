---
name: Bug report
about: 提交漏洞
title: "[BUG]"
labels: enhancement
assignees: ''

---

**描述问题**
描述实际发生的事情，如果可能，请提供完整的异常堆栈。

如果可能，请提供一个最小、完整、可验证的示例，这也有助于检查问题是否与你自己的代码有关。

**截图**
如果有问题图示。

**版本**
列出你的版本、配置，如果可能，检查新版本是否解决。
 - 操作系统: [e.g.  CentOS 7, Ubuntu 18, docker 20]
 - Python: [e.g. 3.8]
 - Sapic: [e.g. 1.16]

尝试列出依赖模块及版本：
```bash
pip list
```

**附录：**
可选：打印配置（SecretKey和Redis地址、密码可用星号代替）

```bash
cd /path/to/sapic/src
python config.py
```
