# 本机项目格式

数据目录中的所有文件都不属于代码仓库。当前版本由操作者或 Codex 准备以下结构，不提供通用自动导入界面。

```text
data-root/
  projects.json
  workflow_routes.json
  workflow_baselines/         # 用户自己的原生工作流
  projects/product-demo/
    batches.json             # ["S01"]
    approval.json
    tracker_status.json      # {"state":"AWAITING_USER_APPROVAL","updatedAt":"ISO时间"}
    events.jsonl
    S01/
      manifest.json
      H3_prompt.txt
      workflow_prepared.json
      assets/
      task_state.json        # 尚未提交时不创建伪任务
      results/               # 由接收脚本生成
```

projects.json结构：

```json
{"schema_version":1,"projects":[{"id":"product-demo","title":"商品测试","path":"projects/product-demo","mode":"queue","conversation":"本机制作","conversation_id":"","updatedAt":"2026-01-01T00:00:00+08:00"}]}
```

初始approval.json必须是未批准状态：

```json
{"status":"AWAITING_USER_APPROVAL","upload_permitted":false,"submit_permitted":false,"workflowId":"由用户填写","approved_batches":[],"planned_waves":[],"excluded_batches":[]}
```

manifest基本字段示例（只是结构，不是可提交样例）：

```json
{"batch":1,"name":"S01","status":"AWAITING_USER_APPROVAL","prompt":"H3_prompt.txt","workflow":"workflow_prepared.json","reference_images":["assets/model.png"],"image_node_ids":["51"],"reference_audio":[],"audio_node_ids":[],"reference_videos":[],"video_node_ids":[],"reference_switch_schema":"native_20260924","depends_on":null}
```

由操作者核对素材文件、原生节点、关闭分支、提示词和工作流差异。批准后approval记录明确批准时间/依据、workflowId、approved_batches中的name与hashes、planned_waves（每波至多3）、excluded_batches。hashes至少覆盖manifest、提示词、工作流和全部参考素材，使用文件SHA-256。不得为了让队列通过而自行改成APPROVED。

项目路径必须在数据目录projects内，批次必须是项目的直接子目录。所有素材和配置使用项目内相对路径；不要指向Downloads或另一台电脑的绝对路径。已提交任务只接受真实返回的taskId。清洁安装不迁移历史授权。

本版新增版本UI沿用已知工作流形态，对不支持的随机种子或节点会拒绝操作；拒绝时需人工适配，不可绕过校验强行运行。

## 可选：跟进页中的参考原片

在项目目录添加 `source_reference.json`，并把视频保存到同一项目内；每次正常render都保留播放器。不设置此文件时原有页面保持不变。原片只作研究/对照，不属于生成上传素材，不会因播放而触发API任务。

```json
{"title":"本地参考原片","video":"reference/original.mp4","origin_url":"https://example.com/source","lark_url":"https://example.com/record","record_id":"来源记录编号","analysis_version":"分析版本","duration_seconds":30,"sha256":"原片SHA256","note":"仅作研究参考","segments":[{"name":"A01","start":0,"end":10},{"name":"A02","start":10,"end":20},{"name":"A03","start":20,"end":30}]}
```

`video`必须是项目内相对路径的现有MP4/WebM；越界或无效配置显示不可用提示，不公开项目外文件。来源链接仅允许http/https，文字转义后显示。`segments`记录原片时间区间，不等同于已实测生成内容的精确动作时间。

## 复刻项目：原片与拼接成片对照

设置source_reference.json的项目默认以对照为首屏：左侧原片、右侧完整拼接结果，同等大小；窄屏上下排列。来源信息及原有分段、版本、队列、任务与异常记录在关闭的折叠区内保留。不存在source_reference.json的项目沿用旧页面。

拼接后添加项目内presentation.json，示例：

```json
{"schema_version":1,"result_video":"review/assembled.mp4","result_label":"新版复刻","duration_seconds":30.2,"audio_language":"印尼语","source_transcript_note":"根据机器转录翻译，未人工听校","source_voiceover":[{"title":"前半段","text":"原片口播中文译文"}],"voiceover":[{"title":"第一段","text":"新片口播中文译文"}]}
```

result_video与原片使用相同的项目内媒体校验。未配置时显示待完成；无效或缺失文件显示暂不可用，不从目录猜选成片。更新已有presentation.json前保留备份，旧成片和输入记录保持原样。此文件仅展示现有媒体和文字，不属于生成授权；不改动冻结的H3提示词、上传素材或taskId。

译文用于中文审阅，成片保持计划确定的目标市场语言。原片机器转录、原片译文、新版计划台词及新版实际转录要区分；机器译文不标为人工听校，中文计划稿不冒称逐字实际成片。视频各自使用原生播放控件，用户自行播放、暂停及调音量，无同步控制或强制静音；不会自动播放、生成或重新拼接。
