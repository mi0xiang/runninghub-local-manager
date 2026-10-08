# V0.2 本机监管与交接

新增 `/supervision.html` 和 `/api/supervision`，保留总管理和历史子页。面板只读取现有项目、任务、归档和交付证据；浏览、刷新不执行云端查询、提交、上传、重试或表格回写。后台摘要不重绘子页。部署时本机 scoped adapter 必须同时适配摘要装饰并关闭隐式子页 render。

全流程界面以九步短中文阶段展示颜色与图标：灰空心未执行、黄时钟等待、蓝轻呼吸执行、绿勾完成、红叹号明确异常、紫人像待人工、灰斜纹问号/琥珀边框待核对。过期或缺失心跳不标红；明确未提交记录与无记录分开。每步支持悬停、键盘focus及点击展开证据，窄屏分成三列。原片/成片移到展开区；首页有“全流程制作面板”入口，监管页返回“生成任务与历史”。既有界面的全绿判定要求各阶段证据、完整技术交付、人工确认和当前版本表格回读齐全；这是现有展示逻辑，不代表用户已确定Lark业务规范。Lark未对接时，本地交付、用户确认与未对接状态分别说明，不把表格回读作为当前本地制作的前置条件；本次仅修订文档，未改变UI判定代码。UI是记录展示，不是监控执行器或围栏启用。

业务阶段、执行、完整交付、人工审核、同步分别记录。ARCHIVED 不等于整片交付；部分原件失败不会抹去其他结果；原件缺失、字节数/哈希变化、流或时长无效、ffprobe 不可用均告警，保留原任务，禁止自动重新生成。归档核验会读取媒体并运行本机 ffprobe；大型媒体会增加刷新耗时。

同一来源和制作版本重复登记保持一个项目；旧登记指向同一物理目录时只派生一套队列任务，原登记和旧任务仍保留。独立视频可同时准备与后期，只有现有统一 FIFO 执行获批批次，并发上限仍为3。当前运行边界以项目规则及[project-runner](project-runner.md)为准：手动、有限、前台接收原task。旧30分钟协调与120秒收片是历史方案，不构成现行周期或后台运行授权。

## 本地入口

使用已经确认的本机配置；测试必须通过 `RUNNINGHUB_CONFIG_FILE` 指向代码目录外的临时数据。

| 命令 | 行为 |
|---|---|
| `manage.py panel` | 生成本地面板和变化事件记录；不调用云服务 |
| `manage.py dashboard` | 临时只读网页服务，POST 返回403，不启动收片器；退出即停止 |
| `manage.py handoff --project ID --record FILE --expected-revision N` | 版本交接；旧版本不可覆盖，身份冲突停止 |
| `manage.py register-ready --record FILE` | 核对已有冻结审批并登记到现有索引；不生成 |
| `manage.py audit-archives --project ID` | 本机原件哈希、媒体核验 |
| `manage.py postproduction-plan --project ID --record FILE --expected-revision N` | 冻结输入、裁剪及音轨方案；缺少质量验收或来源音轨/BGM授权时等待 |
| `manage.py delivery-record --project ID --record FILE --expected-revision N` | 保存完整输出哈希和技术证据；人工审核仍为PENDING |
| `manage.py lark-diff --snapshot FILE` | 从真实快照文件生成本机差异候选，无网络和审批权限 |
| `manage.py lark-receipt --request OUTBOX_FILE --receipt FILE` | 绑定原请求字节哈希和身份接收回执；保留本机成果 |

`postproduction-plan` 和 `delivery-record` 管理前置条件和证据；冻结方案的实际拼接使用 [project-runner](project-runner.md) 中的 `assemble-project`，整片登记使用 `delivery-register`。技术检查不等于人工视觉验收。

## 写入围栏

停掉旧运行时代码后，才可由唯一协调者显式启用数据根 `coordination/writer-authority.json`。本轮未启用或改写生产 authority。格式：

```json
{
  "schema_version": 1,
  "writer_id": "root-coordinator",
  "epoch": 1,
  "code_version": "h3-supervision-v0.2",
  "project_writers": {
    "branch-one": {"paths": ["projects/example"]}
  }
}
```

启用后每次JSON写入核对身份、epoch、代码版本，使用进程锁和读后比较，原JSON按哈希备份在 `coordination/state-history`。分支只写指定项目，共享索引只由协调者写。显式分支交接使用 `--writer branch-one --epoch 1`。不启用时兼容旧数据；绝不能宣称围栏已经保护生产。

围栏是合作式程序约束，不是Windows ACL或凭据机制。没有迁移到新存储入口的旧程序、直接手改文件及原样复制的旧二进制无法被它拦截；部署必须先核实旧服务和共享写入者，停掉旧代码，并将所有参与者迁移到相同围栏协议。换epoch后旧会话拒绝继续写入。不因此启动旧周期协调或替其他聊天接管业务。

## Lark 单记录协议

适用范围：以下保留已有适配器的技术契约，供后续明确采用该接口时核对，不是当前统一业务规范。用户会在子项目指定要复刻的视频与对应Lark单元格；字段、回写内容和对接分工仍按实际需求逐步确定。现有两列接口不限制未来方案，也不会自动成为每个制作项目的必做环节。

该已有接口对齐外部信息收集适配器的 `lark-safe-adapter.schema.json` schema_version1。采用时从本机项目上下文定位实际对端与契约文件；公共包不附对方项目或其路径。请求只有14个契约字段；本地status和may_dispatch放在外层返回值，不写进请求文件。request_id为UUID；两列仅为复刻阶段与复刻任务；expected与desired键集合相同。绑定记录ID、来源键、项目、本地版本、快照UUID、时间和实际文件字节SHA256。目标与字段身份从本机配置读取；它们是私有资源标识，不含访问凭据。

### 可选本机目标配置与升级

采用此适配器时，在配置数据根的 `coordination/lark-target.json` 填写已经核实的目标与字段ID。公共仓库不提供真实目标，不从输入快照自动认领目标。以下仅为合成结构示例：

```json
{
  "schema_version": 1,
  "target": {
    "base_token": "fixtureBaseToken",
    "table_id": "tblFixture",
    "view_id": "vewFixture"
  },
  "fields": {
    "复刻阶段": {"field_id": "fldStageFixture", "type": 3},
    "复刻任务": {"field_id": "fldTaskFixture", "type": 1}
  }
}
```

缺少配置时，新差异候选返回 `LARK_NOT_CONFIGURED`；配置损坏或字段定义不完整时返回 `INVALID_LARK_CONFIGURATION`，均不创建outbox请求。表、视图或字段与快照不一致仍拒绝生成请求。本地制作、成片交付与已有请求回执校验不依赖这份新配置。

从旧固定目标版本升级时，先备份代码及既有outbox/回执，停止受影响的本机进程；将旧版本已核实的目标和字段标识迁入上述数据文件，再更新程序。保留原请求文件字节、UUID、哈希和回执，不用新配置重写历史记录。无需改动 `.local/config.json` 或重置项目。新电脑暂不接入Lark时可省略这份文件。该两列契约只约束选用这个已有适配器的调用，不预设后续业务对接规范。

快照要求ok/live、字段ID及类型匹配、来源与记录唯一、时区明确，最长15分钟有效。缺少实际文件哈希、历史/失败/过期快照均不出可用请求。严格请求保存于数据根 `coordination/lark-outbox/UUID.json`；完全相同的差异复用原文件字节，不修改UUID或时间。过期请求必须先重新inspect，使用新快照和新UUID。

请求文件由信息收集负责方交接到其固定requests目录；**必须逐字节复制H3原文件，不重新序列化**，否则回执摘要无法绑定原请求。H3不会写该项目目录，不内置inspect/commit调用。预览READY只代表检查通过；NO_CHANGE预览不是成功云写回执。本轮没有实际commit或云表修改。

回执校验要求原文件摘要及全部身份对应。APPLIED/NO_CHANGE还要求两列实际readback、readback_at及verified_record_ids。UNKNOWN映射RECONCILE_REQUIRED；不确定或冲突会阻止该项目再生成差异请求，必须人工核对并取得绑定原请求的明确恢复回执后再接续。所有失败均保留本机原件和完整交付，不自动重试。

## 验证范围

完整离线unittest覆盖业务阶段、缺失/损坏归档、旧epoch/旧代码/旧读版本、项目写入范围、冻结后期/音轨、队列去重和独立并发、HTTP200/媒体Range206/只读POST403，以及真实适配器代码在临时目录中的请求预览。

设置 `H3_LARK_ADAPTER` 为对方脚本路径、`H3_LARK_BINDING` 为匹配该适配器的本机目标配置文件、`H3_LARK_EXAMPLE` 为对方integration样例可运行跨端离线fixture；公共测试只使用合成资源标识。实际样例仅按原始文件和冻结历史时钟重现NO_CHANGE，绝不当作新鲜快照或新的批准。没有真实云写入、浏览器视觉审查、完整历史原件验收或生产服务启动验证。

## 两条业务线与职责交接

面板按现有元数据派生 Lark协作 / 自主创作 / 待分类，不自动迁移历史登记。完整 TikTok source_key 与 record_id 可确认 Lark身份；自主项目必须明确 business_line=INDEPENDENT、creation_key、production_version，不借用或制造云端行。冲突与缺失身份保留待分类，不能整行变绿。

既有面板将Lark路线显示为采集、匹配、编剧、审批、队列、生成、归档、后期、验收回写九步；当前制作按用户实际任务推进，回写步骤是否接入以后续对接要求为准。自主路线显示需求、编剧分镜、审批、生成、后期、验收交付六步；队列与归档证据仍可展开查看，共用原全局 FIFO、账号并发上限3。自主路线不需要原片或 Lark 回写，完整成片的技术证据与人工验收仍必需。

新自主登记仅调用既有 register_ready_project；当前冻结 approval.json 必须有效。同 creation_key + production_version 重复登记返回原项目，身份/path冲突拒绝。登记本身不上传、不提交。handoff-state.json / handoffs-v1 是同一版本化交接记录，保留 owner、制作版本和 CAS revision；自主交接带 creation_key，无 source_key/record_id。需求证据可使用 brief.json：schema_version=1、state=CONFIRMED、非空 requirements；也可由既有 handoff.stages.REQUIREMENTS 提供明确状态与 artifacts。

脚本执行确定性队列、原任务查询、下载校验、冻结参数后期与记录；所属子项目负责创意、skill选择、内容质量判断、诊断和具体修复，总项目制定基本规则并跟踪进度与阻塞。内容问题回所属子项目，共享身份/队列异常交协调或维护责任方核对。新增费用、已确认方案的实质变化、删除、发布和最终用户确认按对应授权处理。

既有交接的 decision 可记录 category、evidence列表、next_action、owner（SCRIPT/COORDINATOR/USER）、decision_required布尔值、attempts非负整数、last_progress（带时区时间或null）；不允许夹带 approved 或付费授权。owner枚举是现有技术分类，不代表总项目自动接管制作，也未在本次文档修订中新增枚举值；实际负责子聊天仍从项目归属和交接证据定位。

面板责任栏是待办读取，不表示 AI 已开始工作。现有活动协调对话可读取本地 API / 交接文件跟踪待办，负责子项目按实际授权处理制作事项；读取面板不启动周期协调。尚无真实代理唤醒通道；不新增 AI 后台、定时器或自动花费。未来事件唤醒接入需另行确定权限和执行协议。未知写回结果由主协调核对原请求与真实回执，再决定动作；本地后期/验收成功记录不因 Lark 失败被抹除。
