# 统一岗位池与筛选规则 v2

本轮新增 `jobpilot.py`，仅依赖 Python 标准库。当前交付是 **SQLite 台账 + Markdown 岗位报告 + 命令行审阅入口**，还未嵌入 BossHunter 网页。它保留上游原始评分，并独立检查资格与 JD 质量；不会发送消息或投递申请。

## 运行

从 JobPilot-CN 根目录执行。真实事实文件放在已忽略的 private/ 目录，结构见 `config/candidate-rules.example.json`。

```powershell
$env:PYTHONIOENCODING='utf-8'
python jobpilot.py import-boss --source ../upstream/BossHunter/data/bosshunter.db --profile private/candidate-rules.json
python jobpilot.py report --output data/job-pool.md
```

导入使用独立只读 SQLite 连接的一致性事务，兼容 WAL；不调用上游初始化/迁移函数，不改写上游状态。已经核查当前版本字段，缺少必需列会报错。本地 GET API 仍可作为后续适配入口，本版选择事务读取以避免分页期间数据变化。

其他渠道可以先手工整理成 JSON 数组，通过 `import-json FILE --profile PROFILE` 导入。至少提供稳定 id / source_job_id、source_platform、title、company、jd、url；此入口不代表已实现官网或智联的在线采集。

## 规则

| 状态 | 条件 | 用途 |
|---|---|---|
| 排除 | 社招目标遇到明确校招/应届/在校标签或正文限定；明确届别不匹配；在校身份不符 | 不进入投递候选，高分不能抵消 |
| 信息不足 | JD 少于250个非空白字符、缺少职责表述、Agent标题与正文信息脱节 | 补充 JD 后再评估 |
| 资格待核实 | 校招与接受社招信息矛盾、招聘类型不明、上游校招分类缺少原文证据、年限超出已知经历、地点缺失或不一致 | 核实后重新评估 |
| 待评分 | 没有有效评分理由 | 保留岗位，等待评分 |
| 低匹配 | 资格/质量规则无阻断，原分低于70 | 不优先 |
| 可人工评估 | 上述规则无阻断且原分至少70 | 仍需人工判断，不代表已批准 |
| 来源已移除 | 上游软删除记录 | 保留审计记录，不推荐 |

优先级按表中资格/质量阻断处理，所有问题同时保留：例如短 JD 又有校招问题，报告仍展示两者。BOSS 的 ready 状态和高分不会覆盖本地规则。

字数阈值是可复核的初始启发式，可能误标简短但完整的 JD；年限检测当前以中文标签和常见表达为主，并不是完备语义理解。没有匹配到规则不代表满足所有任职条件，英文要求、专业、签证、学历等仍需人工核对。水印噪声作为警告保留，不修改原始 JD。

校招硬筛选依据当前候选人的 `recruitment_type=experienced` 偏好。明确不符合直接排除；没有证据不推定符合。BossHunter 的招聘类型可能来自宽泛关键词分类，因此单独的 campus 字段只触发待核实；“校园招聘系统开发”等业务描述也不作为校招身份要求。

## 人工审阅与申请记录

报告每条岗位均给出 ID。请仅在真实审阅后记录本人结论：

```powershell
python jobpilot.py review "boss:职位ID" --decision needs_verification --note "需要确认校招资格"
python jobpilot.py review "boss:职位ID" --decision worth_applying --note "本人已核对资格与职责"
python jobpilot.py review "boss:职位ID" --decision unsuitable --note "职责不符"
```

实际提交之后再回填记录（此命令不执行提交）：

```powershell
python jobpilot.py application "boss:职位ID" --state submitted --evidence "本人确认已提交，平台申请编号或成功页本地路径"
```

同一 `(source, source_id)` 重复导入不新增。原始岗位、评分、个人资格配置或规则版本变化后，人工结论重置为未审阅；旧审阅事件和原始快照仍保留。已有申请状态不因重新导入丢失。跨平台同一岗位暂不自动合并，需要人工核实，不能仅按标题合并。

## 数据和测试

- `data/jobpilot.db`：统一台账、原始快照及事件。
- `data/job-pool.md`：当前岗位、问题、人工状态、原始评分理由与来源链接。
- `private/candidate-rules.json`：候选人真实资格依据。
- 所有真实数据都已被 Git 忽略，仓库只提交程序、测试和空白示例。

```powershell
python -m unittest discover -s tests -v
```

测试覆盖高分校招、错误届别、未知毕业年份、低质量高分 JD、年限缺口、未评分、软删除、重复导入、变更撤销旧审核、批次原子回滚和源库结构不匹配。扩展采集另行记录真实运行结果，不以单元测试代替平台验证。
