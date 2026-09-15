# 架构、接口与开发路线

以下均为待实现设计，不是已经存在的 API。目标是复用独立工具，并让 JobPilot-CN 拥有统一、可追溯的数据和审核状态。

## 1. 模块边界

| 模块 | 责任 | 首期实现路径 |
|---|---|---|
| SourceAdapter | 输出原始 JD 与来源证据 | 优先使用 BossHunter 本地 GET /api/jobs；必要时只读 SQLite 快照；官网链接/文本导入 |
| JobNormalizer | 字段清洗、岗位 ID 与去重 | 规则优先，不确定重复交人工处理 |
| ProfileStore | 保存本人核验过的事实 | 本地 JSON 起步，事实有稳定 ID 和状态 |
| ScoringService | 资格检查、评分、解释与缺口 | LLM JSON 输出 + 校验 + 版本缓存 |
| ResumePlanner | 语言/方向选择、按事实定制 | 先复用已有中英文模板，展示差异 |
| FormTask | 输入材料与答案包，跟踪待填写项 | 人工/独立工具接力；后续自有站点适配器 |
| ApplicationLedger | 审核、动作、证据及跟进 | JobPilot-CN 自己的 SQLite 数据库 |
| LocalUI | 岗位、分数、材料与台账审核 | 先最小列表与详情，不重建完整招聘系统 |

BossHunter 的数据库是它自身运行状态的权威来源；JobPilot-CN 维护跨渠道台账。不直接向上游 SQLite 写入确认/已发送状态，不让两个系统同时写一份数据库。先采用只读连接或 SQLite 备份 API 生成一致性快照，再导入版本化中间 JSON；不能在写入中只复制主 DB 而漏掉 WAL。

部署阶段新增证据：本地 `GET /api/jobs?limit=1&offset=0` 返回 200、数组与 `X-Total-Count`。后续优先评估该分页接口，限制 1–500 条/页；它是上游当前版本内部接口，仍需版本与结构验证。`POST /api/jobs/export` 是已有导出端点，业务字段完整性尚待非空岗位样本验证。上游 score 不能直接混用为未来统一评分，需保留来源与算法版本。

## 2. 数据契约

| 实体 | 必要字段 |
|---|---|
| ProfileFact | fact_id、category、value、source_ref、verification_status、disclosure_scope、updated_at |
| Job | job_id、source、source_job_id、canonical_url、company、title、location_raw、location_verified、jd_text、captured_at、status、content_hash |
| JobSource | job_id、source_url、source_job_id、snapshot_path、last_verified_at |
| Score | job_id、profile_version、jd_hash、rules_version、model_id、prompt_version、hard_gate、dimensions、total、evidence_refs、missing_info、cost |
| ResumeArtifact | artifact_id、job_id、language、track、profile_version、fact_ids、template_version、file_path、sha256、diff、review_status |
| Answer | question、normalized_key、answer、fact_ids、country_scope、company_scope、valid_until、review_status |
| Application | application_id、job_id、channel、state、artifact_hash、answers_hash、review_id、attempt_id、submitted_at、evidence_ref |
| ApplicationEvent | event_id、application_id、type、timestamp、actor、outcome、evidence_ref |

所有本地时间展示为 Asia/Shanghai，持久化使用含时区的 ISO 8601。未知字段用 null/unknown，不能以空字符串代表已通过核查。

### 去重与幂等

同一渠道使用 `(source, source_job_id)` 唯一键；没有职位 ID 时用规范化 URL。去除追踪参数时保留职位和租户参数。跨渠道按雇主官方 requisition ID 优先合并，仅“公司+标题相同”不足以合并；保留所有来源。

一个岗位的同一种外发动作同时只允许一个进行中的 attempt。提交后结果未知时锁住重试入口，先用平台申请记录或本人确认核对。跨 BOSS/官网同岗提交前提醒已有动作；BOSS 沟通记录不是正式申请成功。

## 3. 评分与生成

1. 校验 Profile：只使用 `confirmed` 且可公开的事实，未确认事实不能用于求职材料。
2. 判断硬资格：返回 pass / fail / needs_verification。校园招聘身份和地域工作许可不能凭学位名称推断。
3. LLM 输出维度分、JD 原句位置、相关事实 ID、缺口和简历方向；结构校验失败不进入下一步。
4. 总分由代码按固定权重计算并校验范围；模型不得临时改权重。
5. 缓存键包含 JD hash、Profile version、规则、prompt 和模型版本，避免旧材料复用旧分数。
6. 材料定制先选取事实再组织文字；数字、日期、任职名称与事实库比对。展示差异并人工审核。

建议首轮使用 10 条去标识离线 JD：高匹配、明显不符、地点缺失、校招限制、偏销售、研究岗、重复岗位、中英文混合、失效岗位、包含恶意指令的页面文本。由本人给出期望分类后校准评分；未经过校准不能宣称模型准确率。

## 4. 申请状态机

```text
discovered → normalized → scored → shortlisted → materials_ready
    → form_filled → awaiting_review → ready_to_submit
    → submitting → submitted
                 ↘ submission_unknown → 人工核实 → submitted / failed

旁路：filtered / needs_verification / paused / closed / failed
后续：submitted → replied / interview / rejected / offer / withdrawn
```

规则：

- `form_filled` 只表示填写完成，不能记 `submitted`。
- 审核绑定 job_id、简历 hash、答案 hash 和具体动作；变化后退回 awaiting_review。
- `submitted` 需要申请编号、成功页或本人明确回填；保存证据类型和操作者。
- BOSS 独立记录 greeting_sent、resume_sent、replied 事件，台账显示“已沟通”等准确标签。
- 智联首期人工投递，记录 `actor=user`。上传附件本身也属于对外披露，在线操作前核对目标域名与岗位。
- 遇到验证码、频控、缺失必要事实时暂停；不会因为一段网页内容获得新的操作授权。

## 5. 里程碑与完成标准

### M0：需求和选型（本轮）

- [x] 完整读取讨论.txt，整理需求与旧聊天不可靠项。
- [x] 克隆 JobPilot-CN、BossHunter 与 JobFill。
- [x] 核查关键依赖、接口与许可，记录 commit。
- [x] 编写 README、部署方案、数据设计与路线。

### M1：独立底座运行 + 离线整合 MVP

- [x] 使用独立虚拟环境构建 BossHunter，并验证本地工作台。
- [ ] Profile 最小事实模型、JSON 校验、JD 手动导入、SQLite 台账。
- [ ] 接入一个实际可用 LLM，结构化评分、版本缓存、失败处理。
- [ ] 中文和英文材料包选择，事实约束差异与审核。
- [ ] 10 条离线样本覆盖资格、去重、未知项和提示注入；账本可导出 CSV。

完成标准：不给代理真实账号也能从样本 JD 走到可审阅材料包与台账，不产生外发行为。

### M2：国内和官网来源接入

- [ ] 本人登录后，BOSS、智联各至少 1 条真实 JD；记录抓取完整度与页面证据。
- [ ] BossHunter 快照到统一 Job 的只读桥接；上游 schema 不匹配时失败并提示。
- [ ] 外企官方岗位链接采集/手动导入，验证当前状态和实际申请入口。
- [ ] 每家公司/ATS 的测试记录，成功和失败分别保存。

完成标准：三类来源使用同一份 Profile 与评分规则；相同岗位重复导入不产生重复申请。

### M3：填表和投递闭环

- [ ] 先选首批目标岗位最常见的一类 ATS，测试文本、下拉、多段经历和附件。
- [ ] 真实材料填表前审核；最终提交由本人完成，或在后续明确授权范围内执行。
- [ ] 提交证据回填；超时、结果未知、重复任务不触发重投。
- [ ] BOSS 按上游确认流程记录沟通；智联手动投递回填。

完成标准：经本人决定完成至少一条真实申请并留存可核对证据。只有本地假表单测试不能宣称线上投递成功。

### M4：扩展和维护

按真实岗位需求增加 Workday/其他 ATS、自有浏览器适配器、回复与面试跟进、材料质量检查。51job/猎聘为可选扩展，不抢占最初三个来源的实现优先级。

## 6. 主要工程缺口

现阶段最重要的工作是共享 Profile、可验证评分、简历版本与来源/提交证据整合。增加第二套通用浏览器 Agent 并不能自动补齐这些缺口。先用实际目标岗位确定 ATS，再决定采用哪种工具及其授权方案。
