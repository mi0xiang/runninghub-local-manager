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
