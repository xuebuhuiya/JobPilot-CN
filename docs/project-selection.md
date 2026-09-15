# GitHub 项目选型与核查

初次源码核查日期：2026-09-15。选型重点是 BOSS + 智联覆盖、Windows 部署成本、可解释评分、真实履历约束、可审核操作及集成成本。未用 Star 数代替适配性或可用性测试。后续本机安装与浏览器连接结果见 [部署验收](deployment-status.md)，下文保留选型阶段的证据范围。

## 1. 结论

**BossHunter 作为国内独立底座；JobFill 下载供外企辅助填表评估；JobPilot-CN 自建统一整合层。**

BossHunter 直接覆盖两项国内来源且有本地工作台，最接近当前需求。JobFill 无需单独部署后端即可评估常见 ATS 的填表能力，适合先减少重复输入；但其授权和适配边界使其暂不成为本仓库代码依赖。

## 2. 候选对比

| 项目 | 本轮证据层级 | 适合复用的部分 | 主要不足 | 决策 |
|---|---|---|---|---|
| [BossHunter](https://github.com/shengjidaguai-china/BossHunter) | README、依赖文件、CLI、配置、SQLite 代码、LICENSE；已克隆 | BOSS/智联采集、评分、本地岗位工作台 | 智联投递手动；不覆盖外企 ATS；非商业许可 | 首选国内底座 |
| [JobFill](https://github.com/Thesirloc/job-autofill) | README、manifest、存储和 Workday 适配源码；已克隆 | 多标签简历、当前页面填表、问答草稿 | 未找到 LICENSE；Workday 多步骤与控件仍需逐页检查 | 独立评估，不复制源码 |
| [ApplyPilot](https://github.com/iknalos/ApplyPilot) | GitHub README / 根目录列表，未下载 | Greenhouse/Lever 问题映射，复杂站点代理思路 | 美国语境问题较多；本地代理依赖 Claude；授权未确认 | 备选，不作为首期依赖 |
| [Auto-Fill-Forms](https://github.com/w4seemdev/Auto-Fill-Forms) | GitHub README / 根目录列表，未下载 | Profile / 问答规则 / 投递日志工作流 | 更接近 Claude Code + Playwright MCP 操作手册；平台数量是作者声明；授权未确认 | 设计参考 |
| [boss-auto-apply](https://github.com/yeatssc/boss-auto-apply) | GitHub README，未下载 | 履历母库、匹配与定制闭环思路 | BOSS 单平台；额外工具链；不解决智联与外企主需求 | 暂不采用 |

以上候选均未通过本机真实招聘网站端到端测试。不把作者文档中的成功率或覆盖数量当作本项目承诺。

## 3. 已下载版本

| 项目 | 版本 / commit | 上游提交时间 | 本地目录 |
|---|---|---|---|
| BossHunter | 2.4.0 / `059bbe9d5c5cc306040cbdf387ac0680c00a1449` | 2026-09-13T22:44:05+08:00 | `../upstream/BossHunter` |
| JobFill | manifest 0.1.2 / `c595088e0024cb29cb09d45b34f5a427d098c839` | 2026-05-17T21:06:44+05:30 | `../upstream/job-autofill` |

上游时间只描述选取的提交，不推断项目未来维护质量。机器可读信息见 [upstream.lock.json](../upstream.lock.json)。

## 4. 源码检查发现

### BossHunter

- [pyproject.toml](https://github.com/shengjidaguai-china/BossHunter/blob/059bbe9d5c5cc306040cbdf387ac0680c00a1449/pyproject.toml) 声明 Python 3.10+；前端构建产物需先生成再安装包。
- [上手指南](https://github.com/shengjidaguai-china/BossHunter/blob/059bbe9d5c5cc306040cbdf387ac0680c00a1449/docs/quickstart.md) 要求 Node.js 22+、Chrome 与 AI API；BOSS 与智联的发送边界不同。
- [配置示例](https://github.com/shengjidaguai-china/BossHunter/blob/059bbe9d5c5cc306040cbdf387ac0680c00a1449/config.example.yaml) 中智联键为 `zhilian`，默认关闭；采集顺序默认仅 `boss`。需在配置面板显式启用智联，不能以默认配置声称已覆盖。
- [main.py](https://github.com/shengjidaguai-china/BossHunter/blob/059bbe9d5c5cc306040cbdf387ac0680c00a1449/src/bosshunter/main.py) 有分步 `scrape`、`score`、`greet` 等入口；初期仅使用采集与评分，不直接运行包含发送环节的完整流程。
- [db.py](https://github.com/shengjidaguai-china/BossHunter/blob/059bbe9d5c5cc306040cbdf387ac0680c00a1449/src/bosshunter/db.py) 使用 SQLite，整合层可设计为只读采集快照导入。不要让两个系统直接修改同一个数据库。

### JobFill

- [manifest.json](https://github.com/Thesirloc/job-autofill/blob/c595088e0024cb29cb09d45b34f5a427d098c839/manifest.json) 明确匹配 Greenhouse / Lever / Workday 域名。自定义公司域名不能一概认为受支持。
- [workday.js](https://github.com/Thesirloc/job-autofill/blob/c595088e0024cb29cb09d45b34f5a427d098c839/content/adapters/workday.js) 主要做站点识别、附件定位和当前页面控件定位；不能由此认定跨页完整填表成功。
- [storage.js](https://github.com/Thesirloc/job-autofill/blob/c595088e0024cb29cb09d45b34f5a427d098c839/lib/storage.js) 保存 Profile、简历及填表 history；该 history 不是招聘平台提交成功凭证。
- README 宣称支持自定义模型端点，但 manifest 的主机权限为明确域名清单。实际自定义端点是否能请求需要另行验证。

## 5. 许可与整合方式

- BossHunter 快照 [LICENSE](https://github.com/shengjidaguai-china/BossHunter/blob/059bbe9d5c5cc306040cbdf387ac0680c00a1449/LICENSE) 是 PolyForm Noncommercial 1.0.0，README 明示商业使用需另行授权。因此它是个人使用场景的候选，不是无约束商业产品底座。
- JobFill 当前下载快照未找到 LICENSE 文件；“公开可见”不能作为可自由复制、修改和再分发的依据。本轮只记录原仓库链接和下载版本，不将代码复制或重新打包进 JobPilot-CN。
- ApplyPilot 与 Auto-Fill-Forms 本轮未完成许可审计，暂不引入代码。后续采用前先确认明确授权。
- JobPilot-CN 保存自行编写的需求、接口和编排代码；上游独立存放。进程隔离不自动消除原有许可条件。

## 6. 尚待验证

1. 本机依赖安装和前端构建已通过，见部署验收；其他平台业务验证仍待完成。
2. 当前账户下 BOSS、智联登录和完整 JD 采集是否正常。
3. 评分接口、材料质量与调用费用是否合适。
4. 第一批外企实际使用的 ATS、必填问题和附件行为。
5. 选用组件的授权是否覆盖未来分发/商业计划。

本阶段完成的是可复核选型，不是在线运行验收。
