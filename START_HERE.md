# 新电脑与新对话接手

这是空白公共程序，原用户的历史项目和授权没有打包在内。

1. 阅读 README.md、AGENTS.md，确认本目录为代码目录。
2. 若无 `.local/config.json`，使用 manage.py init 初始化仓库外的数据目录，再 doctor 和 confirm。确认只允许本机程序运行，不授权生成视频。
3. 从配置定位数据目录；读取 projects.json 选定项目。不要默认处理最新项目，也不要使用另一台电脑的路径。
4. 新项目按 docs/project-format.md 准备，初始 AWAITING_USER_APPROVAL。给用户复核素材、提示词、工作流及参数后才能批准上传/生成。
5. 已有项目先读 approval.json、batches.json、task_state.json、events.jsonl 与结果目录。有 taskId 查原任务；未知提交状态先查平台，不能重提。
6. 完成后在该本机项目追加 handoffs.md，记录时间、完成项、遗留项和下一步；更新本地页面。不要把这个记录提交到代码仓库。

给新对话的指令：请阅读“本代码目录”的 AGENTS.md 和 START_HERE.md，从 .local/config.json 定位本机数据，核对项目、批准和原任务ID后接手。代码更新用 Git，生成结果不参与同步。
