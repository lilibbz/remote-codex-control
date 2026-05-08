# Remote Codex Control

中文 | [English](README.md)

Remote Codex Control 是一个 Codex skill，用来把手机上的指令发送到电脑端 Codex App，并在手机上查看 Codex 的处理结果。

它的核心场景是：你正在电脑上让 Codex 处理一个工程项目，突然需要出门，但还想用手机继续指挥当前这个 Codex 工程线程。手机负责提交指令，电脑端 Codex 线程负责读取、执行，并把简短结果写回手机页面。

## 它能做什么

- 在电脑上启动一个带 token 保护的轻量 HTTP 桥接服务。
- 给手机提供一个适合移动端使用的指令页面。
- 把手机提交的指令保存到电脑本地 `inbox.jsonl`。
- 让 Codex 读取、确认、完成或跳过手机指令。
- 手机页面可以看到最近指令的状态和结果说明。
- 支持通过 Tailscale 在外网/蜂窝网络下访问家里或办公室的电脑。
- 提供可选的 event worker，用于不依赖当前聊天记忆的独立后台任务。

## 推荐架构

```text
手机浏览器
  -> Tailscale 私有 IP
  -> 电脑端桥接服务
  -> inbox.jsonl
  -> 当前 Codex App 线程通过手动检查或 heartbeat 读取
  -> 手机页面显示结果回执
```

推荐使用“当前线程控制”模式。这样可以保留当前 Codex App 的聊天上下文、工程决策和工作区状态。

## 环境要求

- 电脑端安装 Codex App。
- Python 3.10 或更新版本。
- 手机和电脑都安装 Tailscale，用于出门后远程访问。
- 手机浏览器。

不需要路由器端口转发，也不推荐做端口转发。

## 安装

把这个仓库克隆到 Codex skills 目录：

```powershell
cd $HOME\.codex\skills
git clone https://github.com/lilibbz/remote-codex-control.git
```

然后重启或刷新 Codex App，让 skill 可以被识别为：

```text
$remote-codex-control
```

## 一次性配置 Tailscale

1. 在电脑上安装 Tailscale。
2. 在手机上安装 Tailscale。
3. 两台设备登录同一个账号或同一个 tailnet。
4. 确认手机和电脑在 Tailscale App 中都显示在线。
5. 可选：用 `ping` 测试两台设备能否互通。

## 出门前启动

在电脑 PowerShell 中运行：

```powershell
cd $HOME\.codex\skills\remote-codex-control
python .\scripts\away_session.py --mode tailscale --port 8765 --reset-token
```

脚本会打印类似这样的链接：

```text
Phone URL over Tailscale: http://100.x.y.z:8765/?token=...
```

把完整链接发到手机上，并在手机开启 Tailscale 后用浏览器打开。

PowerShell 窗口不要关闭。需要停止远程访问时，在该窗口按 `Ctrl+C`。

## 发送测试指令

在手机页面的 `Command` 输入框里输入：

```text
测试：如果收到这条手机指令，请回复我。
```

点击 `Send to desktop Codex`。如果页面显示 `Sent: ...`，说明指令已经成功到达电脑端收件箱。

## 当前线程控制模式

在电脑端当前 Codex App 线程中，让 Codex 检查一次：

```text
使用 $remote-codex-control 检查一次手机指令收件箱。
```

也可以创建一个有时间边界的 heartbeat：

```text
接下来 4 小时内，每 30 分钟使用 $remote-codex-control 检查一次手机指令收件箱。如果有待处理指令，就在当前 Codex App 线程中执行，并写入简短的手机可见结果说明。
```

这是推荐模式，因为它让当前 Codex App 线程继续掌控工程上下文。

## 手动操作收件箱

在 skill 目录下运行：

```powershell
python .\scripts\read_inbox.py list
python .\scripts\read_inbox.py next --mark-seen
python .\scripts\read_inbox.py done <command-id> --note "已完成：修改了 X，并验证了 Y。"
python .\scripts\read_inbox.py skipped <command-id> --note "需要澄清：..."
```

手机页面会每隔几秒刷新最近指令状态。

## 可选 Event Mode

Event mode 会启动一个本地 Python watcher。它空闲时只轮询本地文件，不消耗模型额度；当手机提交新指令时，它会启动一个独立的非交互式 `codex exec` 任务，并把结果写回手机页面。

它只适合不依赖当前 Codex App 聊天记忆的独立任务：

```powershell
python .\scripts\away_session.py --mode tailscale --port 8765 --reset-token --event-worker --workdir C:\path\to\your\project
```

如果你需要延续当前 Codex App 的工程对话和上下文，不要使用 event mode，优先使用手动检查或 heartbeat。

## Token 和额度说明

Heartbeat 检查即使没有新指令，也会消耗一定使用额度。一次 ChatGPT Plus 实测中，2026-05-08 进行的 5 次每分钟 heartbeat 空检查，大约消耗了用户 5 小时 Plus 使用窗口的 4%。这只是粗略参考，实际消耗会受模型、上下文长度、是否执行任务等因素影响。

推荐频率：

- 每 60 分钟：最低消耗，适合偶尔更新。
- 每 30 分钟：推荐默认值。
- 每 15 分钟：响应更快，消耗中等。
- 每 5 或 10 分钟：只建议短时间紧急使用。

建议设置明确的持续时间，比如“接下来 4 小时”。

## 安全注意事项

- 不要公开带 token 的手机链接。
- 每次新的外出会话建议使用 `--reset-token` 生成新 token。
- 不要通过手机页面发送密码、API key 或其他敏感信息。
- 优先使用 Tailscale 或其他私有 VPN。
- 不要把 `8765` 端口直接暴露到公网。
- 不要做路由器端口转发。
- 不需要远程访问时，及时停止桥接服务。

更多说明见：

- [references/security.md](references/security.md)
- [references/away-access.md](references/away-access.md)

## 验证

运行：

```powershell
python -m py_compile .\scripts\away_session.py .\scripts\event_worker.py .\scripts\read_inbox.py .\scripts\start_mobile_bridge.py
python .\scripts\away_session.py --help
python .\scripts\read_inbox.py list
```

如果这个仓库已经安装为 Codex skill，也可以验证 skill 结构：

```powershell
python $HOME\.codex\skills\.system\skill-creator\scripts\quick_validate.py $HOME\.codex\skills\remote-codex-control
```

## 项目状态

这是一个早期但可用的实用原型。稳定核心包括：手机指令收件箱、Tailscale 远程访问、当前线程手动/heartbeat 控制、手机端结果回显。

后续可改进方向：

- 更好的手机端 UI。
- 指令搜索和过滤。
- 按设备区分指令。
- 在 token 之外增加本地 PIN。
- 更顺滑的安装向导。
- 为桥接 API 增加自动化测试。
