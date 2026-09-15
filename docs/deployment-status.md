# 本次部署验收：2026-09-15

## 已完成

| 项目 | 结果 |
|---|---|
| 上游 | BossHunter 2.4.0，commit 059bbe9d5c5cc306040cbdf387ac0680c00a1449 |
| Python | 3.11.3，独立 `.venv`，普通 wheel 安装 |
| 前端 | Node 24.15.0 / npm 11.12.1；269 个包；TypeScript + Vite 构建成功 |
| 依赖检查 | `pip check`：No broken requirements found |
| CLI | `bosshunter --help` 成功列出命令 |
| 服务 | `127.0.0.1:8686`；`GET /api/health` 返回 status=ok、version=2.4.0 |
| 页面 | 浏览器实际打开工作台、配置页；页面显示本地服务运行中 |
| 配置 | 上海，AI 应用 / Agent / RAG；BOSS 与智联启用；各关键词最多 1 页；自动评分关闭 |
| 模型 | DeepSeek / `deepseek-flash` / `https://api.deepseek.com`；并发 1；Key 未填写 |
| 浏览器 | 独立 Chrome 用户目录，9222；内置 Browser Runtime 3456；CLI connect 确认已连接 Chrome |
| 岗位接口 | `/api/jobs?limit=1&offset=0` 返回 200、`[]`、X-Total-Count=0 |
| 启动脚本 | 从未运行状态启动成功；再次执行识别已有服务，不重复启动 |

DeepSeek 地址和当前模型名依据 [官方首次调用文档](https://api-docs.deepseek.com/) 于本日核对；模型可用权限与真实调用仍须填入本人 Key 后测试。没有消耗模型对话 Token，也没有执行申请提交。

依赖实装版本见 [bosshunter-windows-installed.txt](bosshunter-windows-installed.txt)。该文件是本机安装清单，不是跨系统通用锁文件。

## 遇到的问题及修复

1. **npm ENOTCACHED**：执行环境被设为仅使用缓存。此次安装显式关闭离线模式，下载成功。
2. **Vite spawn EPERM**：受限环境无法启动 esbuild 子进程。获准使用正常执行环境后构建成功。仅有 bundle 大小提示，无编译错误。
3. **editable 安装后 ModuleNotFoundError**：.pth 文件含 UTF-8 中文路径，本机 Python 3.11 未将该路径加入 sys.path；源路径实际存在。设置 UTF-8 运行标志仍未解决。改为普通 wheel 安装后 CLI 与配置导入成功。

未修改上游跟踪源码，未升级全局 Python/Node/npm，未修改全局代理或关闭 TLS 验证。

## 日常使用入口

- `start-workbench.cmd`：启动后台工作台并打开配置页，已有健康服务时复用。
- `open-job-browser.cmd`：打开独立求职 Chrome 与 BOSS/智联首页，供本人登录。
- `scripts/start-workbench.ps1`：只启动服务，不主动打开浏览器。
- `scripts/start-job-browser.ps1`：默认隐藏空白浏览器供连接检查；传 `-Show` 打开人工登录窗口。

当前服务是本次手动启动，未配置开机自启。双击入口调用 `-ExecutionPolicy Bypass` 仅作用于本次 PowerShell 进程，不更改机器持久执行策略。

## 数据位置

- 上游本地配置：`../upstream/BossHunter/config.yaml`（Git 已忽略）。
- 上游数据库：`../upstream/BossHunter/data/`。
- Key：由上游面板单独保存到已忽略的本地凭据文件；不要提交或复制到公开日志。
- 专用 Chrome 登录数据：`private/chrome-profile/`（Git 已忽略）。
- 工作台进程信息及日志：`data/runtime/`（Git 已忽略）。

## 本人需要完成的三项输入

1. 在 [配置页](http://127.0.0.1:8686/config) 的「AI 设置」输入 DeepSeek API Key，保存后测试连接。
2. 在同页「个人信息」上传真实简历，补充准确学历和校招/社招类型。
3. 双击 `open-job-browser.cmd`，在专用 Chrome 中登录 BOSS 与智联。不要只在 Codex 内置浏览器登录，BossHunter 当前连接的是另一个独立 Chrome 会话。

准备好后先做少量“单独采集”，检查 JD 完整度，再评分。当前登录状态未验证、真实岗位数为零，不能将已连上 Chrome 当作已登录平台。

## 下一开发阶段

统一岗位池优先使用本地只读分页接口导入；先保留原始 JD、平台 ID、来源状态及上游评分，后续建立独立统一评分和材料版本。此阶段尚未编写桥接、统一评分或简历生成代码。
