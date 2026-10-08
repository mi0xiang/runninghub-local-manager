# RunningHub Local Manager

Windows 本机视频生成追踪中心。代码可通过 GitHub 更新；任务、参考素材、视频、工作流及运行日志只保存到各电脑自己的数据目录。

后续更新新增只读 `/supervision.html`、交接版本、原件核验及Lark差异协议；部署、围栏启用和本地命令见 [监管与交接说明](docs/supervision-v02.md)。本机后期技术通过仍须人工审核。

这是独立社区工具，并非 RunningHub 或 MiniMax 官方产品。当前源码包含 **0.1.0 之后的更新**，版本标签以 GitHub Releases 为准。支持空白安装、项目网页、30项分页、队列状态、既有任务查询下载、已批准任务提交和版本管理。云端端到端生成未在此独立版重新验收。

## 快速安装

需要 Windows 10/11、Python 3.12+；下载校验与合成需要 FFmpeg 和 FFprobe。核心 Python 代码仅使用标准库，无需安装创意模型或 Codex 才能浏览页面。准备新项目可由 Codex 辅助。

1. 将代码解压或 Git 克隆到任意盘，例如 `F:\Apps\runninghub-local-manager`。
2. 在该目录运行以下命令。数据目录必须在代码目录外；初始不含任何项目。

```powershell
python manage.py init --data-dir 'F:\RunningHubData' --ffmpeg 'F:\ffmpeg\bin\ffmpeg.exe' --ffprobe 'F:\ffmpeg\bin\ffprobe.exe'
python manage.py doctor
python manage.py confirm
python manage.py dashboard
```

也可以运行 `powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1` 按提示填写。

浏览器打开 `http://127.0.0.1:18765/supervision.html`。`dashboard` 是只读、手动前台服务，Ctrl+C 停止；浏览页面不启动收片或生成。仅监听本机回环地址，端口固定18765，不用于公网/局域网部署。环境检查报告位于数据目录 `环境检查.html`。

原有 `manage.py web` 仍保留：先渲染历史页面，再启动带操作按钮和每2分钟原任务收片的服务（常规查询从提交满8分钟开始），与只读 `dashboard` 行为不同。`start.ps1` 默认 Web 模式也进入这个原有入口。当前制作采用下文的只读展示与有限收片；是否使用旧入口按所在项目授权决定。

## 哪些需要填写

| 配置 | 保存位置 | 用途 |
|---|---|---|
| 数据目录 | `.local/config.json` | 本电脑项目和成片位置，可选 F 盘 |
| Python | 初始化自动记录 | 后台调用解释器 |
| ffmpeg、ffprobe 路径 | `.local/config.json` | 下载后校验与后期合成 |
| RUNNINGHUB_API_KEY | Windows 当前用户环境变量 | 仅调用 API 时需要，不写入仓库 |
| 工作流及工作流ID | 本机项目和批准记录 | 操作者自行导出、核验、批准 |

新配置、移动代码目录、移动数据目录或换电脑后需重新 doctor/confirm。修改数据目录前先复制需要保留的数据；本工具不替你同步。空白安装无需复制任何旧数据。API变量缺失时可浏览；FFmpeg缺失时无法完整执行下载归档和合成。报告明确区分必需检查和功能警告。

## 手动执行与原有队列入口

按 [有限收片说明](docs/project-runner.md)准备准确项目、负责聊天和原 taskId 的选择清单，然后手动执行 `python manage.py watch-results --selection <清单.json>`。达到终态、时长或错误预算后停止；关闭后不继续运行，重启接续原记录。


`python manage.py tick` **可能上传素材、提交已批准任务**，不是只读命令。只有经过明确批准的项目进入提交队列。

```powershell
# 单次处理
python manage.py tick
# 原有可选能力：只有明确授权定时提交时才使用；当前手动制作流程不启用
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1 -Mode InstallQueueTask
```

安装、打开页面或读取本说明均不授权注册计划任务。若另行明确启用上述旧能力，计划任务名为 `RunningHub-Local-Manager`；删除/禁用此任务可停止定期调度。任务只在用户登录时运行。退出 Codex 不影响已注册调度；退出网页服务不会取消云端任务。账户并发最大3，不应让多台机器同时调度同一个项目的副本。

## GitHub 更新，不同步结果

仓库仅有程序、通用指引模板、说明和合成测试。`.local/`、`.project-local/` 被忽略；数据目录强制位于仓库外。不要把本机数据目录提交到 GitHub，不要使用 `git add -f` 绕过忽略规则。发布检查读取实际Git暂存内容，见[发布说明](docs/publishing.md)。

更新前关闭受影响的网页、收片与队列进程；仅当本机确实安装过 `RunningHub-Local-Manager` 计划任务时禁用它。备份本机数据与 `.local/config.json`，再执行：

```powershell
git status --short
git pull --ff-only
python -m unittest discover -s tests -v
python manage.py doctor
python manage.py confirm
python manage.py dashboard
```

有未提交代码修改时，先处理差异，不强制覆盖。先看 CHANGELOG，再决定更新。当前无自动远程更新、自更新服务、遥测或跨机同步；除操作者执行 Git 更新外，生成相关网络调用仅针对 RunningHub 和其输出下载地址。

## 总项目与子项目指引

[指引模板与跨机接手说明](templates/project-guidance/README.md)随Git更新，包含总入口、子入口及复刻咨询、音画检查、页面边界和条件适用的H3指引。无需另外发送通用AGENTS；每台电脑按实际项目填写自己的私有上下文。

模板安装默认预览，明确应用后才写入代码仓库外的项目目录；已有或定制规则报告差异，不直接覆盖。Git拉取只更新模板源，安装过的项目按差异合并；原始商品知识、来源单元格、路径和历史任务不进模板。同账户多电脑需要唯一调度端或已验证的共同协调机制，当前3并发是共享账户上限。

## 操作与开发资料

- `START_HERE.md`：新对话/新操作者接手。
- `AGENTS.md`：开发、提交批准、数据隔离规则。
- `docs/project-format.md`：准备一个本机项目的数据结构。
- `docs/workflow-rules.md`：H3原生参考节点与修改边界。
- `docs/local-controls-and-versions.md`：网页、队列、版本操作。
- `docs/project-runner.md`：全片计划、有限收片、冻结后期与交付登记。
- `docs/supervision-v02.md`：监督页与可选 Lark 本机目标配置、迁移说明。
- `docs/publishing.md`：公共仓库发布范围和步骤。
- `templates/project-guidance/README.md`：总/子项目指引模板、私有上下文、安装与更新。
- `安装指引.html`：不需要编辑器即可查看的简明指引。

公共包不附第三方工作流导出、模型、收费技能、个人素材或历史授权。现阶段需按文档准备项目，不是任意 ComfyUI 工作流的一键适配器。
