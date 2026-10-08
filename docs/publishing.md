# 公共仓库与发布

建议仓库名 runninghub-local-manager，Public，MIT。仓库仅管理本目录中的代码、通用指引模板、文档和合成测试；不是数据备份仓库。

公开前运行测试并检查 `git diff --cached`。不要上传本机 `.local` 配置、`.project-local` 上下文、商品知识、来源链接/单元格、真实账号与资源标识、用户工作流、API Key、控制令牌、项目、历史对话、任务响应、截图或成片。本机数据目录位于代码目录外；不能为了同步而搬回仓库。

[项目指引模板](../templates/project-guidance/README.md)只维护通用规则和合成示例。实际总/子项目AGENTS可能包含隐私及本机路径，不能直接导出整个项目作为模板；逐层核对所引用的指引、示例、安装说明及生成源。只有公开模板的固定文件清单参与安装，私有上下文不反向复制。

提交前运行`python scripts/check_public_tree.py`，检查的是Git暂存区所有文件的实际字节及模式，包括先前已被跟踪的文件。它拒绝超出发布目录的路径、私有目录、媒体/二进制/符号链接，并报告常见凭据、个人路径和真实形态的Lark标识所在文件与行；不打印匹配值。Git忽略规则无法移除已有跟踪内容。这是辅助检查，不能识别所有隐私或判断资料授权，仍须人工审阅本次差异及完整发布包。CI重复同一检查；本地审查在上传之前完成。

首次发布可在 GitHub 建空仓库后执行（将 OWNER 替换为自己的账号）：

```powershell
git init -b main
# 先逐项核对实际目录内容；只暂存审阅过的文件，不使用 git add . 或 -f
git add README.md AGENTS.md START_HERE.md CHANGELOG.md LICENSE .gitignore manage.py setup.ps1 start.ps1
# 其余 scripts/web/docs/tests/templates/.github 等文件按审阅清单逐项添加
python scripts/check_public_tree.py
git diff --cached --stat
git commit -m "Initial clean local manager"
git remote add origin https://github.com/OWNER/runninghub-local-manager.git
git push -u origin main
```

如果仓库已存在，先核对远端内容，不覆盖或强推。依赖第三方工作流的原件不随MIT程序授权发布，使用者应自行获取。

维护建议：代码修改走分支和PR；Windows CI运行无网络/无付费测试；发布版本标签并说明配置/数据迁移影响。更新仅用 git pull --ff-only，不自动修改数据，不自动启动任务。Release ZIP从已审查的准确提交导出，检查完整文件清单与内容，包含templates，排除缓存、配置、历史与Git内部目录。不要对工作目录直接压缩打包。
