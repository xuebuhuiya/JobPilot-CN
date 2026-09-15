# Windows 实际部署方案

本文给出后续可执行步骤，**本轮只完成源码下载和静态检查，以下安装、配置与业务操作尚未执行**。先部署独立工具，再开发统一流水线。

## 1. 部署结构与依赖

单台 Windows 电脑、本地浏览器、单用户。BossHunter 使用独立 Python 虚拟环境；Node.js 用于前端和浏览器运行时；JobFill 是可选 Chrome 扩展。首期无需云服务器、Docker、Redis 或向量数据库。

上游要求 Python 3.10+、Node.js 22+、Chrome。当前 PATH 找到 Python、Node、npm 与 Git，但未完成版本/安装健康检查，也未核实 Chrome 安装位置。BossHunter 的 AI 服务在本地面板配置，模型名与 Key 以实际服务为准。

## 2. 复现源码下载

当前工作区已有下述两个独立克隆。仅在新电脑或目录尚不存在时执行：

```powershell
# 从 JobPilot-CN 仓库根目录开始
New-Item -ItemType Directory -Force ..\upstream | Out-Null
git clone https://github.com/shengjidaguai-china/BossHunter.git ..\upstream\BossHunter
git -C ..\upstream\BossHunter checkout 059bbe9d5c5cc306040cbdf387ac0680c00a1449
git clone https://github.com/Thesirloc/job-autofill.git ..\upstream\job-autofill
git -C ..\upstream\job-autofill checkout c595088e0024cb29cb09d45b34f5a427d098c839
```

若已有工作副本，更新前先检查本地修改，不覆盖用户配置。以后升级先更换测试副本、重新验收，再更新锁定版本。

本机下载时，默认 Git 连接失败指向不可用的 `127.0.0.1` 代理；单次去掉代理后又遇到 Schannel 凭据错误。最终通过下面的命令级参数成功克隆，没有修改全局 Git 配置，也没有关闭 TLS 校验：

```powershell
git -c http.proxy= -c https.proxy= -c http.sslBackend=openssl clone <仓库URL> <新目录>
```

只在允许直连、遇到相同问题时使用该参数，不是通用安装前提。

## 3. 安装 BossHunter

```powershell
Set-Location ..\upstream\BossHunter
python --version
node --version
npm.cmd --version
python -m venv .venv
npm.cmd --prefix src/bosshunter/web/frontend ci
npm.cmd --prefix src/bosshunter/web/frontend run build
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\bosshunter.exe --help
.\.venv\Scripts\bosshunter.exe web --no-open
```

逐条执行并检查退出码；任一步失败先修复再继续。使用 `npm.cmd` 避免 PowerShell 对 npm.ps1 的执行策略差异；使用虚拟环境的绝对相对入口，无需激活脚本。必须先构建前端，因为源码仓库没有预生成的 frontend/dist。

启动后在浏览器打开 `http://127.0.0.1:8686`。该命令会占用终端，后续命令在另一个终端进入同一目录运行。

参考：[上游固定版本安装说明](https://github.com/shengjidaguai-china/BossHunter/blob/059bbe9d5c5cc306040cbdf387ac0680c00a1449/docs/quickstart.md)。

## 4. 配置与国内试运行

1. 在面板提供本人核验过的履历文件，填入城市、岗位关键词、招聘类型等。不要沿用上游“北京 / 15–25K”等示例偏好。
2. 配置 AI 服务和模型；API Key 只在本地填写。
3. 在平台设置启用 BOSS 与智联（配置键 `boss`、`zhilian`），设置串行采集顺序。先小样本、少页面，禁用未经审核的发送。
4. 根据上游指南连接独立 Chrome 会话，并在该会话内由本人登录平台；远程调试只用于本机，不开放到局域网或公网。
5. 执行连接检查：

```powershell
.\.venv\Scripts\bosshunter.exe ai-status
.\.venv\Scripts\bosshunter.exe connect
```

6. 首次通过面板分别选择 BOSS 和智联进行小样本采集，核对实际来源和完整 JD。CLI 的 `scrape` 不能在未核实多平台路由时被当作覆盖智联的证据。
7. 对已采集样本评分：

```powershell
.\.venv\Scripts\bosshunter.exe score
.\.venv\Scripts\bosshunter.exe status
```

第一阶段不执行 `run` / `send`。后续本人审核后再使用 BOSS 发送功能；智联在平台手动提交并记录结果。BOSS 打招呼、发简历和 ATS 提交申请是不同事件，不能混为“已投递”。

## 5. 外企辅助填表评估

JobFill 当前未找到 LICENSE，仅保留原仓库本地评估副本。它不是 JobPilot-CN 已集成的插件，也不是本方案完整运行的必要依赖。

若进行本地评估：Chrome 扩展管理页 → 开发者模式 → 加载已解压的扩展 → 选择 `upstream/job-autofill`。根据上游 README，可以直接加载仓库根目录，无需先打包。

首先使用虚构测试资料验证控件；通过后再在本地填写本人 Profile 和简历。选择一个真实目标岗位，按其最终申请 URL 判断是否属于 Greenhouse、Lever 或 Workday：

- 选择正确语言与方向的附件。
- 填写当前页，核查教育/工作历史、日期、下拉框和文件名。
- Workday 每页继续核查；未识别控件改为手工填写。
- 开放题由本人确认后使用；授权、薪资与资格问题不能猜测。
- 最终提交由本人完成，保存平台成功页或申请编号；扩展的填表历史不能证明提交成功。

JobFill 与统一 Profile 之间尚无同步桥接。第一阶段手动录入经过核验的信息，后续再做自有映射/导出层。未知 ATS 先手动填写，再按实际使用频率安排适配。

## 6. JobPilot-CN 整合层部署目标（待开发）

选择 Python + SQLite + 本地 Web 页面作为初始方案：

- BossHunter 只读快照导入和官网 JD 导入。
- 统一 Profile / JD / Score / ResumeArtifact / Application 模型。
- LLM 结构化评分和事实约束定制。
- 本地岗位列表、简历差异审核和投递台账。
- 通过附件包/表单任务将材料交给独立工具或本人操作。

当前不存在 `jobpilot run`、API 服务或可一键部署的完整程序，不能使用虚构命令。开发顺序与验收见 [架构路线](architecture-roadmap.md)。

## 7. 运行验收与故障处理

| 检查 | 通过标准 | 未通过处理 |
|---|---|---|
| 环境 | 前端构建、包安装、CLI 帮助均成功 | 保留错误日志，先修依赖 |
| 国内采集 | BOSS/智联各至少 1 条完整且来源正确的 JD | 验证登录、配置与页面结构；可暂用手动导入 |
| 外企采集 | 1 条官网 JD，含岗位 ID、地点和当前申请链接 | 详情页失效则标记关闭/待核实 |
| 模型 | 同一份履历与 JD 得到可解析结果及证据 | 校验失败有限重试，随后待人工处理 |
| 简历 | 中英文各一份无虚构事实，附件正确可读 | 退回修改，不能进入提交队列 |
| 填表 | 核查每页字段与最终附件，没有误提交 | 未识别项人工接管 |
| 记录 | 填完、提交成功、结果未知可明确区分 | 无凭证标记未知，先核对再重试 |

API 超时可重试只读步骤；发生发送/提交超时不能直接重复动作。验证码、频控、登录失效先暂停。停机后保留状态，恢复时重新验证页面与材料版本。

## 8. 数据与成本

真实 Profile、简历和申请证据放在 JobPilot-CN 的 `private/` / `data/` / `artifacts/` 等已忽略目录。BossHunter 自己的配置和数据库仍位于独立副本，备份时同样按个人资料处理。JobFill 的 Chrome 本地存储不是加密保险箱，导出包可能包含 Key，不能提交 Git。

成本记录按模型实际 token 用量和服务商账单计算。先用小批样本量出每条 JD 的均摊费用，再设置每天金额与调用次数上限；本文不预设未经核实的价格。
