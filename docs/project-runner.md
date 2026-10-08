# H3 子对话全流程负责与有限收片

每个新子对话负责自己的整条视频，从审批内提交、持续接收原task、分段验收与真实帧续接，到按冻结分镜后期、整片内容检查、成片登记和追踪回读。总主管负责跨项目FIFO／最多3并发、去重、遗漏与超时提示；共享脚本提供机械执行。监督页只读，打开网页不会启动任务或唤醒聊天。

总/子项目协作入口可从[公共模板](../templates/project-guidance/README.md)按本机项目适配；真实来源、业务资料、私有例外及工具位置由本地上下文定位。模板不规定固定技能、商品或创作表格。本说明约束实际执行接口；同账户的3并发由统一调度协调，不是每台电脑各3个。

子对话不能以“已提交API”“成功返回URL”“下载了一段”作为整片完成。遇到审批、失败、未知提交或人工内容判断时，保存确切断点和责任子对话、说明下一步；不得改成完成。

## 手动启动与恢复

`manage.py watch-results --selection <本地选择清单.json>` 是前台、有限时长、仅收已有task的程序。所选原task均终态、错误预算耗尽、达到有限时间或Ctrl+C时停止。窗口／程序关闭后不继续执行；重启读取相同清单对应的 `coordination/receive-runs/<选择哈希>.json`，保留原task、错误预算和退避时间。它不上传、不create、不重试付费生成、不启动聊天、不安装服务／系统任务／开机自启。

```json
{
  "schema_version": 1,
  "projects": [{
    "project_id": "已登记项目ID",
    "ownerThreadId": "负责子对话ID",
    "task_ids": ["该项目已有taskID"]
  }],
  "poll_seconds": 120,
  "max_minutes": 120,
  "max_errors": 5
}
```

选择须精确匹配项目、负责子对话及原批次中的task ID，不接受未知或重复ID。`--once` 只做一轮；`--resume-errors` 用于人工核对原因后解除本次查询错误预算，仍只收原ID。查询错误保存为收片阻塞，不冒称平台生成失败。锁占用时延后；原记录在查询期间变化时保留新记录并要求核对。

收片不创建队列行、不调整FIFO／审批／并发。只在统一hub锁内刷新所选已有队列行及自己项目的tracker_status，保留其他项目、顺序、审批指纹和提交次数。选择锁避免重复启动；原task与档案校验避免重复下载。现有可选写入权限栅栏继续生效；没有启用它的机器也使用文件锁与摘要比较写入，不能据此宣称已启用全局权限栅栏。

## 全片计划与依赖

`execution-plan --project <ID> --record <JSON> --expected-revision <当前修订号>` 登记自己项目的execution-plan.json。包含生产版本、ownerThreadId、按全片时间排列的全部片段、请求时长、初末状态、依赖；新H3请求每段不超过15秒。登记不批准、不入队、不提交。复用本地片段使用 `kind: local_media`、项目内文件和SHA256，不当成新H3请求。历史审批、失败／取消任务和task ID保持原样。

原FIFO门禁保留，并核对执行计划的依赖。后段依赖前段实际验收时，使用 `segment-review` 按修订号登记原task、原文件SHA256、明确内容结论与本地证据；需要真实稳定帧时，绑定实际帧、SHA256、人工接受和证据。不能用“已下载”替代商品、口播或稳定帧验收。`project-status --project <ID>` 及现有监督页列出全片计划，包括尚未准备／审批的后段及负责子对话。

## 原文件与冻结后期

收片器保留视频及单独音轨节点的nodeId、类型、URL、字节数、SHA256与FFprobe结果；检查非空、HTTP Content-Length（有值时）和媒体类型。过期URL仅有界刷新原任务输出一次，不create。原始文件不覆盖为剪辑成片；损坏档案转阻塞，人工核对恢复。

`assemble-project --project <ID> --owner <负责子对话ID>` 只执行现有postproduction.json中经postproduction_records检查的READY冻结方案：内容证据、全部输入／哈希、全片顺序、实际裁剪范围与明确音轨方式。外部音轨需要已有授权；不同视频格式、缺音轨、未批准音轨、超出实际时长或次序不符会阻塞，不能猜补。单独音轨已收存；自动拼接当前支持视频内生成音轨或明确指定整片原音轨／BGM，逐段独立音轨需另行冻结映射方案后处理。

执行保留原文件，核对输出时长、音轨有无及全文件解码，写assembly.json与版本化输出。相同输入／方案／输出哈希重复执行复用；已有不同版本输出不覆盖。技术检查不等于商品、衣服外观、动作、口播、音画匹配和接缝的内容验收。

## 成片登记与完成

负责子对话检查整片并登记delivery.json中的技术证据和content_review（ACCEPTED、ownerThreadId、成片哈希、实际本地证据）。让自己的presentation.json与子项目页真实指向完整成片，再调用 `delivery-register --project <ID> --owner <负责子对话ID> --expected-revision <delivery修订号>` 核对文件、页面和监督数据回读。登记仅为REVIEW_PENDING，不能替用户confirmed；GET200、视频Range206与播放检查仍需子对话给出证据。

兼容现行记录的状态对应：submitted／queued／running在task_state；success输出就绪为CLOUD_SUCCEEDED；downloaded为ARCHIVED／DOWNLOADED；validated为哈希／媒体／解码证据；assembled在assembly.json；review为登记与人工PENDING；confirmed只来自绑定准确版本和哈希的用户确认；failure保留平台失败与诊断。缺段、技术／内容不合格或未经登记回读都不能标整片完成。

## 升级与回退

先备份选定项目状态和受影响共享账本，记录范围／原始哈希／活动子对话；活动项目隔离，不替其改媒体或页面。测试用临时配置／数据及合成ID／视频。全量测试与编译检查后恢复原手工只读网页入口。回退可恢复本轮code-before，执行计划历史修订保留；原审批／task／原视频不可删除或覆盖新分支工作。测试与修复不上传、create、付费重试、Lark写入或自动启动。
