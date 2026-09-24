# RunningHub Local Manager

Windows 本机视频生成追踪中心。代码可通过 GitHub 更新；任务、参考素材、视频、工作流及运行日志只保存到各电脑自己的数据目录。

这是独立社区工具，并非 RunningHub 或 MiniMax 官方产品。当前为 **0.1.0 初始版**，从已有本地工具抽取。支持空白安装、项目网页、10项分页、队列状态、既有任务查询下载、已批准任务提交和版本管理。云端端到端生成未在此独立版重新验收。

## 快速安装

需要 Windows 10/11、Python 3.10+；下载校验与合成需要 FFmpeg 和 FFprobe。核心 Python 代码仅使用标准库，无需安装创意模型或 Codex 才能浏览页面。准备新项目可由 Codex 辅助。

1. 将代码解压或 Git 克隆到任意盘，例如 `F:\Apps\runninghub-local-manager`。
2. 在该目录运行以下命令。数据目录必须在代码目录外；初始不含任何项目。

```powershell
python manage.py init --data-dir 'F:\RunningHubData' --ffmpeg 'F:\ffmpeg\bin\ffmpeg.exe' --ffprobe 'F:\ffmpeg\bin\ffprobe.exe'
python manage.py doctor
python manage.py confirm
python manage.py web
```

也可以运行 `powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1` 按提示填写。

浏览器打开 `http://127.0.0.1:18765/index.html`。Web 命令会保持前台运行，Ctrl+C 停止服务。仅监听本机回环地址，端口固定18765，不用于公网/局域网部署。环境检查报告位于数据目录 `环境检查.html`。

## 哪些需要填写

| 配置 | 保存位置 | 用途 |
|---|---|---|
| 数据目录 | `.local/config.json` | 本电脑项目和成片位置，可选 F 盘 |
| Python | 初始化自动记录 | 后台调用解释器 |
| ffmpeg、ffprobe 路径 | `.local/config.json` | 下载后校验与后期合成 |
| RUNNINGHUB_API_KEY | Windows 当前用户环境变量 | 仅调用 API 时需要，不写入仓库 |
| 工作流及工作流ID | 本机项目和批准记录 | 操作者自行导出、核验、批准 |

新配置、移动代码目录、移动数据目录或换电脑后需重新 doctor/confirm。修改数据目录前先复制需要保留的数据；本工具不替你同步。空白安装无需复制任何旧数据。API变量缺失时可浏览；FFmpeg缺失时无法完整执行下载归档和合成。报告明确区分必需检查和功能警告。

## 本机后台队列

`python manage.py tick` **可能上传素材、提交已批准任务**，不是只读命令。只有经过明确批准的项目进入提交队列。

```powershell
# 单次处理
python manage.py tick
# 可选：明确输入 START 后注册当前用户每2分钟的本机任务
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1 -Mode InstallQueueTask
```

计划任务名 `RunningHub-Local-Manager`；删除/禁用此任务可停止定期调度。任务只在用户登录时运行。退出 Codex 不影响已注册调度；退出网页服务不会取消云端任务。账户并发最大3，不应让多台机器同时调度同一个项目的副本。

## GitHub 更新，不同步结果

仓库仅有程序、说明和测试。`.local/` 被忽略；数据目录强制位于仓库外。不要把本机数据目录提交到 GitHub，不要使用 `git add -f` 绕过忽略规则。

更新前关闭网页服务，禁用 `RunningHub-Local-Manager` 计划任务并确认后台进程结束。备份本机数据与 `.local/config.json`，再执行：

```powershell
git status --short
git pull --ff-only
python -m unittest discover -s tests -v
python manage.py doctor
python manage.py confirm
python manage.py web
```

有未提交代码修改时，先处理差异，不强制覆盖。先看 CHANGELOG，再决定更新。当前无自动远程更新、自更新服务、遥测或跨机同步；除操作者执行 Git 更新外，生成相关网络调用仅针对 RunningHub 和其输出下载地址。

## 操作与开发资料

- `START_HERE.md`：新对话/新操作者接手。
- `AGENTS.md`：开发、提交批准、数据隔离规则。
- `docs/project-format.md`：准备一个本机项目的数据结构。
- `docs/workflow-rules.md`：H3原生参考节点与修改边界。
- `docs/local-controls-and-versions.md`：网页、队列、版本操作。
- `docs/publishing.md`：公共仓库发布范围和步骤。
- `安装指引.html`：不需要编辑器即可查看的简明指引。

公共包不附第三方工作流导出、模型、收费技能、个人素材或历史授权。现阶段需按文档准备项目，不是任意 ComfyUI 工作流的一键适配器。
