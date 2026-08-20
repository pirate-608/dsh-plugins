<!-- dsh-package-header -->
# @pirate-608/dsh-zju-learning-tools

Read and separately approve bounded ZJU learning operations。

先安装到 DSH profile，再创建独立 Preset：

```powershell
dsh plugin --profile web add @pirate-608/dsh-zju-learning-tools
dsh plugin --profile web exec dsh-zju-learning-tools preset install
dsh plugin --profile web exec dsh-zju-learning-tools doctor
```

受管 Preset：`zju-read`、`zju-submit`。标准 Preset 不会得到本包的工具或技能；MCP 写操作和未知工具必须经过一次性审批。
<!-- /dsh-package-header -->

# ZJU Learning Tools

ZJU Learning Tools 是面向 Windows DSH 的本地插件，用于安全查询“学在浙大”和部分智云
课堂数据、下载用户有权访问的官方课程资料，并可选地把用户已经审阅的文件提交到普通作业。
插件通过本地 stdio MCP 运行，统一认证密码不会进入 DSH 上下文。MCP 传输不可用时，独立且
受限的 tronclass-cli 回退可继续少量查询和下载任务。

## 能力

- 查询学年、学期、课程、章节、活动和待办。
- 查看作业元数据、本人提交历史、课程进度、成绩和测验状态。
- 只读查看问卷、签到通知和讨论，不答题、不签到、不发帖。
- 列出课程/个人资源，按用户明确选择下载，并校验路径、大小和 SHA-256。
- 查询智云课堂日程、已有 PPT 页面元数据和转写结果。
- 通过默认关闭的“准备—确认—提交”事务，将已审阅文件提交到一个普通作业，并锁定 SHA-256、
  逐次确认和写后核验。
- 在确认 MCP 启动、握手、工具注册或传输故障后，用固定的 tronclass-cli 0.2.8 回退查询
  待办/课程/活动/作业列表，或下载一个已确认附件。

插件不能提交考试、测验、随堂练习或问卷，不能代签或枚举签到码、发布讨论、撤回既有提交、
伪造位置/设备/进度、刷视频、批量/定时提交、自动重试不确定写入或绕过下载限制。

## 按任务拆分的 Skills

插件包含八个相互独立的 Skill，使 Agent 只加载当前任务所需的工作流与安全约束：

- `$zju-auth-session`：运行环境诊断，以及由用户本人完成的登录、状态检查和登出指导。
- `$zju-course-planning`：学期、课程、待办、活动与进度整理。
- `$zju-assignment-grades`：作业截止时间、本人提交历史、反馈与成绩查询。
- `$zju-assignment-submission`：受控准备并一次性提交用户已审阅的普通作业文件。
- `$zju-resource-downloads`：资源定位、明确确认、限量下载与哈希汇总。
- `$zju-assessments-discussions`：只读查询测验、问卷、签到通知与课程讨论。
- `$zju-zhiyun-classroom`：智云课堂日程、PPT 元数据与已有转写。
- `$zju-tronclass-fallback`：MCP 传输不可用时的受限降级查询与下载。

认证只是各流程的共同前置条件，不会扩大权限。只有 `$zju-assignment-submission` 可以调用两个
固定的作业写入工具，其余 Skill 对校园系统保持只读。

## 要求与安装

- Windows 10/11
- `PATH` 中已有 [uv](https://docs.astral.sh/uv/)
- 能访问相应浙大服务的网络
- 本人账号对目标课程和文件具有访问权限

将本仓库添加为 DSH 插件市场，再安装 `zju-learning-tools`。运行时依赖由
`runtime/uv.lock` 锁定；首次使用可能需要下载公开 Python 依赖。

请在你本人打开的 PowerShell 中执行登录：

```powershell
powershell -ExecutionPolicy Bypass -File .\plugins\zju-learning-tools\scripts\zju-auth.ps1 login
```

密码使用终端隐藏输入且不会保存。随机会话加密密钥保存在 Windows Credential Manager，
加密且会过期的 Cookie 会话位于
`%LOCALAPPDATA%\pirate-608\zju-learning-tools\`。插件不会读取已安装 ZLA 或浏览器的凭据。

将参数换成 `status` 或 `logout` 可检查或清除会话。CAS 出现验证码、二次认证或表单变化时，
登录会安全停止并提示使用官方页面，不会无限重试。

## MCP 不可用时的 tronclass 回退

只有 MCP 进程无法启动、无法注册工具、握手失败或传输中断时才使用回退。普通的
`auth_required`、限流、权限、契约变化或工具错误不会触发回退。隔离环境通过
`fallback/uv.lock` 固定为 tronclass-cli 0.2.8 与 Python 3.9；首次使用可能下载该 Python
运行时与锁定的公开依赖。

请由你本人配置并认证这套独立会话：

```powershell
powershell -ExecutionPolicy Bypass -File .\plugins\zju-learning-tools\scripts\zju-fallback.ps1 configure
powershell -ExecutionPolicy Bypass -File .\plugins\zju-learning-tools\scripts\zju-fallback.ps1 login
```

受限包装器会禁用 tronclass-cli 读取和保存密码的 keyring 行为，并强制使用固定 ZJU 后端。
CLI 原本未加密的 shelve 会话会加密存放到
`%LOCALAPPDATA%\pirate-608\zju-learning-tools\tronclass-fallback\`，密码不会保存。回退仅开放
待办、课程、活动列表/安全元数据、作业列表字段和一个明确选择的下载；学期、详细成绩/历史、
个人资源、测验、讨论、问卷、签到与智云均返回 `fallback_unsupported`。

包装器拒绝任意 tcc 参数、API URL、重定向、非浙大下载主机、不安全路径、覆盖与超过
250 MiB 的文件。它绝不会调用 `tcc homework submit`；作业准备和提交没有 CLI 回退。
执行 `zju-fallback.ps1 logout` 可删除回退会话。

## 作业提交

安装后作业提交默认关闭。请在你本人打开的交互式 PowerShell 中授权一个或多个本地目录：

```powershell
powershell -ExecutionPolicy Bypass -File .\plugins\zju-learning-tools\scripts\zju-write-access.ps1 enable -Root D:\path\to\reviewed-homework
```

脚本会显示权限范围，并要求手动输入 `ENABLE ASSIGNMENT SUBMISSION`。策略保存在
`%LOCALAPPDATA%\pirate-608\zju-learning-tools\`，不保存密码。使用 `status` 检查，或用
`disable` 关闭。

每次提交分为两个阶段：

1. `zju_prepare_assignment_submission` 重新读取作业与本人提交历史，核验普通作业类型和截止时间，
   对每个明确文件计算 SHA-256，并返回 120 秒有效的预览；这一步不执行远端写入。
2. 用户核对账号尾号、作业、既有提交次数、文件路径/大小/SHA-256、评论、截止时间和 payload
   哈希后，必须重新明确确认，才允许调用一次 `zju_commit_assignment_submission`。
3. commit 再次核验账号、权限、作业版本、截止时间、路径、大小和哈希，随后上传、提交一次，
   再读取提交历史确认结果。

Approval 仅在当前 MCP 进程有效、会过期且不能复用；本地原子 ledger 会跨重启阻止完全相同的
重复提交。写入开始后发生超时或结果不明确时返回 `submission_state_unknown`，必须到官方页面
检查，禁止自动重试。插件不会在同一自主流程中把刚生成的作业直接提交。

## 下载规则

Agent 必须先列出资源，并得到用户对上传 ID、文件名和现有绝对目标目录的明确确认。默认不覆盖
同名文件，而是生成 `-v2` 等版本；文件经同目录临时文件写入后原子改名。限制为单文件
250 MiB、每批 50 个、每批总计 1 GiB，并阻止路径穿越、UNC、ADS、重解析点和非白名单重定向。

校园 API 没有公开契约，可能随时变化。CI 仅使用 Mock 服务与脱敏 fixture，不会对生产校园
域名执行写测试。首次真实提交应由用户选择低风险、体积小的普通作业附件，并同时核对官方页面。

## 让 AI 自动配置插件市场

复制以下 Prompt 给 DSH：

```text
请添加 Git 插件市场 git@github.com:pirate-608/codex-plugins.git，检查其中的市场元数据，安装
zju-learning-tools，并确认本机 uv 可用。不要向我索要浙大密码或 Cookie。安装完成后，给出需要
由我本人在本地 PowerShell 执行的认证命令，并提醒我新建一个 DSH 任务后再测试 zju_doctor。
```

## 许可证

插件自有代码使用 MIT。隔离的 `vendor/lazy-core` 兼容组件来自
[LAZY v0.2.6](https://github.com/YangShu233-Snow/Learning_at_ZJU_third_client)，继续使用
LGPL-3.0-only。可选锁定回退依赖 MIT 许可证的 tronclass-cli 0.2.8。详见
`THIRD_PARTY_NOTICES.md` 和 `UPSTREAM.json`。未引入 LAZY 的 AGPL Server。
