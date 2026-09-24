# 公共仓库与发布

建议仓库名 runninghub-local-manager，Public，MIT。仓库仅管理本目录中的代码、文档和合成测试；不是数据备份仓库。

公开前运行测试并检查 `git diff --cached`。不要上传本机 `.local` 配置、用户工作流、API Key、控制令牌、项目、历史对话、任务响应、截图或成片。本机数据目录位于代码目录外；不能为了同步而搬回仓库。

首次发布可在 GitHub 建空仓库后执行（将 OWNER 替换为自己的账号）：

```powershell
git init -b main
git add README.md AGENTS.md START_HERE.md CHANGELOG.md LICENSE .gitignore manage.py setup.ps1 start.ps1 scripts web docs tests .github 安装指引.html
git diff --cached --stat
git commit -m "Initial clean local manager"
git remote add origin https://github.com/OWNER/runninghub-local-manager.git
git push -u origin main
```

如果仓库已存在，先核对远端内容，不覆盖或强推。依赖第三方工作流的原件不随MIT程序授权发布，使用者应自行获取。

维护建议：代码修改走分支和PR；Windows CI运行无网络/无付费测试；发布版本标签并说明配置/数据迁移影响。更新仅用 git pull --ff-only，不自动修改数据，不自动启动任务。Release ZIP使用明确代码文件列表，排除缓存、配置、历史与Git内部目录。
