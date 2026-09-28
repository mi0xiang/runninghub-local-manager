# RunningHub Local Manager · agent rules

Read START_HERE.md before acting. Code root is this file's directory; load `.local/config.json` to locate THIS machine's data root. Never infer a historical drive path. API keys come only from RUNNINGHUB_API_KEY; never print or serialize them.

## Local data boundary
Git contains program code, documentation and synthetic tests only. Projects, workflows, task IDs, approval records, logs, media and control tokens belong outside the repository. Do not copy data into examples/tests, commit `.local`, or force-add ignored files. Public releases must be built from an explicit code file list and inspected before upload. No telemetry, cloud data sync or public server deployment.

## API actions
New uploads/generation, revised versions and failed reruns require explicit user approval for exact assets/batches/parameters. Setup confirmation is not generation approval. Existing task IDs must be reconciled, never blindly submitted again. Unknown submission outcomes stop automatic generation. Maximum account concurrency3, global FIFO. Retain native approval hashes and original task records.

Use manage.py / scripts/hub.py as entry points; do not directly invoke legacy core module main functions. tick and UI resume/fetch can advance approved work and are not read-only. No paid/network tests in CI. Confirmation applies only to the current machine, code path and configuration.

## 工作流 2097955216049131522：每次调用必读（2026-09-28）

准备、修改、重跑或提交该工作流前，先读 [docs/workflow-rules.md](docs/workflow-rules.md)，核对本次原生导出及哈希。**265 的实际参考输入连接是 API 执行图的判定依据**，不能只看界面开关或上传清单。

| 参考类型 | 按顺序使用的加载节点 | 上传返回 fileName 写入 | 265.inputs 中的入口 |
|---|---|---|---|
| 图片1–8 | 51、49、50、43、19、23、199、200 | LoadImage.inputs.image | ref_images.ref_image_0…7 |
| 音频1–3 | 48、14、15 | LoadAudio.inputs.audio | ref_audios.ref_audio_0…2 |
| 视频1–3 | 27、25、26 | VHS_LoadVideo.inputs.video | ref_videos.ref_video_0…2 |

- 先按用途选择素材：身份图、穿着静帧、产品图等分别列明顺序；仅供分析或后期合入的音视频不作为生成参考。三类独立计数、分别使用前 N 路，提示词引用顺序与清单一致。
- 开启：保留本次需要的原生加载节点，并让265对应入口连接 `["节点ID", 0]`；获批后逐份上传，将每个返回的fileName绑定到该素材对应的image/audio/video字段，并同步nodeInfoList。
- 关闭：准备稿中移除265未使用的参考入口，以及仅服务于该参考的未使用加载分支；不上传该路，不用空字符串、None、旧文件名冒充关闭。删除前检查是否还有其他消费者，存在共享连接或与原生基准不符时停下复核，不能误删采样链。
- 307/308/309为界面图片/音频/视频分组开关；已核实导出的inputs为空。禁止构造它们不存在的API布尔字段；仅修改nodeInfoList的文件名也不等于关闭265连接。
- 示例：3图+2音频+2视频，仅保留图片51/49/50、音频48/14、视频27/25及265对应入口；其余参考关闭。3图无音视频时，265不得保留任何ref_audios.*、ref_videos.*入口，三个音频和三个视频加载分支都不使用。
- 提交前逐类检查：素材文件数 = 节点ID数 = 265启用入口数 = 上传绑定数；路径、文件哈希、类别、序号、字段及远端fileName可追溯。数量、顺序或字段不一致必须停止，不能静默截断或复用另一素材的返回值。
- native_references.configure/verify当前只覆盖音视频原生分支，不代表图片已自动配置或完整三类校验已实现。图片另行准备复核；更多图片节点从已核实的八图原生基准获取，不能凭编号补造。
- 保留内部音频VAE、解码器、模型、采样、缩放/二采放大及其他连接。所有参考开关差异在批准前保存；批准后只按获批映射写上传返回值，不临时改图。每个新版本/失败重跑仍需具体提交批准；已有taskId不重提。本规则更新不代表云端端到端验证通过。

## Maintenance
Test modifications in an isolated temporary data directory using RUNNINGHUB_CONFIG_FILE. Never point tests at real project data. Run `python -m unittest discover -s tests -v`, compile Python files, and inspect the public archive. Stop services before changing executable code. Record material changes in CHANGELOG. Existing machine data schema changes require backup and documented migration; updates must never reset records. Keep all service bindings loopback-only.
