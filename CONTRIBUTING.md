Contributing
============

感谢您的贡献！

Bug
---

在GitHub中新建 [Issue](https://github.com/staugur/picbed/issues/new)：

- 描述实际发生的事情，如果可能，请提供完整的异常堆栈。

- 如果可能，请提供一个最小、完整、可验证的示例，这也有助于检查问题是否与你自己的代码有关。

- 列出你的Python、Flask、picbed版本、配置，如果可能，检查新版本是否解决。

  ps：打印配置（SecretKey和Redis地址、密码可用星号代替）

    ```
    $ cd /path/to/picbed/src
    $ python config.py
    ```

Feature
-------

同样是在GitHub中新建 [Issue](https://github.com/staugur/picbed/issues/new)，提出功能需求，描述下其具体要求。

Pull Request
------------

**首先是环境**

- Fork [picbed](https://github.com/staugur/picbed)

- 检出/克隆picbed，并设置好: `git config`

  如果您不是最新fork，需先同步picbed最新代码，参考官方文档：[Syncing a fork](https://help.github.com/en/github/collaborating-with-issues-and-pull-requests/syncing-a-fork)

  请在dev分支编写代码。

- 基础环境与安装过程参照 [picbed文档](https://picbed.rtfd.vip/install.html)

**接着是编码**

- 编写代码，请尽量遵守 [PEP8规范](https://www.python.org/dev/peps/pep-0008/)。

- 如果可能，编写测试用例，建议的吆。

- 如果可能，分别使用py2.7、py3.5+运行测试: ``make test``

- 如果可能，请编写文档，位于docs下，构建文档(py3)：

  ```
  $ cd /path/to/picbed/docs
  $ python3 -m pip install -r ../requirements/docs.txt
  $ make html
  ```

**最后合并请求**

- 提交代码

- 在GitHub上发起合并到dev分支的``pull request``

钩子扩展
---------

如果您开发了一个钩子扩展，欢迎提交到[Awesome for picbed](https://github.com/staugur/picbed-awesome)
