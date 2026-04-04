# ClaudeSafeOps

**AI 驱动的服务器运维，内置风险管控。**

用自然语言管理服务器 — 多层安全引擎确保危险命令在没有你明确批准的情况下永远不会执行。

[English](README.md)

---

## 为什么选择 ClaudeSafeOps

传统运维：手动写命令，祈祷不会手滑 `rm -rf /`。

ClaudeSafeOps：告诉 AI 你想做什么，**115 条风险规则** + **4 个安全 hooks** + **审计追踪** 确保即使 AI 犯错，也不会造成灾难。

```
你说：  "清理 web-01 上的旧日志"
AI 执行：ssh web-01 'find /var/log -name "*.gz" -mtime +30 -delete'
引擎：  ⚠️ 中风险 — 文件删除，确认执行？[y/N]
```

```
你说：  "删掉测试数据库"
AI 执行：ssh db-01 'DROP DATABASE test'
引擎：  🔴 严重风险 — 已拦截。需走审批流程。
```

## 两大核心支柱

### 1. AI 自动化

| 特性 | 说明 |
|------|------|
| **自然语言运维** | 用中文/英文/韩文告诉 Claude 做什么，自动构造 SSH 命令 |
| **九大运维模块** | system、network、disk、process、deploy、backup、security、log、playbook |
| **剧本系统** | 保存验证过的运维方案为 YAML 剧本，支持 `{{变量}}` 参数化复用 |
| **语言自动适配** | Claude 自动检测你的语言，CLI 输出自动匹配（en/zh/ko） |
| **快捷命令** | `/onboard`、`/health`、`/audit`、`/risk`、`/playbook`、`/lang` |

### 2. 风险管控

| 防御层 | 机制 | 拦截对象 |
|--------|------|----------|
| **Hook: sensitive-input-guard** | 用户消息发送前拦截 | 对话中输入的密码/Token/密钥（阻止发送到 AI） |
| **规则引擎** | 115 条正则规则（CRITICAL/HIGH/MEDIUM/LOW） | `rm -rf /`、`DROP DATABASE`、`shutdown`、`kill -9` |
| **Hook: risk-check** | Bash 工具调用前拦截 | SSH/scp/rsync/ansible 命令风险评估 |
| **Hook: guard-files** | Write/Edit/Read/Glob 调用前拦截 | 篡改 hook 配置、读取凭据/SSH 密钥 |
| **Hook: validate-hooks** | Bash 首次调用时检查 | 检测安全 hooks 是否被移除或配置错误 |
| **Hook: audit-log** | Bash 调用后记录 | 所有远程操作写入 JSONL 审计日志 |
| **凭据隔离** | 文件权限 + getpass | 密码永远不出现在日志、命令行参数或代码中 |
| **文件隔离** | `~/.claude-safe-ops/` 分离 | `git pull` 永远不覆盖你的配置和凭据 |

## 30 秒上手

```bash
git clone https://github.com/zhouhao4221/claude-safe-ops.git && cd claude-safe-ops
./install.sh
vim ~/.claude-safe-ops/config/hosts.yaml   # 添加你的服务器
claude                                      # 启动 Claude Code
```

然后直接说：

> "帮我检查 web-01 的磁盘空间"
>
> "nginx 配置没问题的话帮我重启"
>
> "看看最近有没有 SSH 暴力破解"

## 安全架构

### 纵深防御

```
用户（自然语言）
  │
  ▼
Claude Code（AI 构造命令）
  │
  ├── /risk ──────────► 执行前预评估风险
  │
  ▼
┌─────────────────────────────────────────────────────────┐
│  Hook 层（.claude/settings.json）                        │
│                                                         │
│  0. sensitive-input-guard.sh — 拦截聊天中的密码/密钥      │
│  1. validate-hooks.sh  — 验证安全组件完整性               │
│  2. risk-check.sh      — 远程命令风险评估                 │
│  3. guard-files.sh     — 保护敏感文件                     │
│  4. audit-log.sh       — 记录所有操作                     │
└─────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────┐
│  风险评估引擎（src/risk/engine.py）                       │
│                                                         │
│  115 条内置规则 + 自定义 YAML 规则                        │
│  优先级: 用户自定义 > 项目 YAML > 内置 Python 规则         │
│  默认: 未匹配命令 → MEDIUM（需确认）                       │
└─────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────┐
│  执行决策                                                │
│                                                         │
│  LOW      → 自动执行                                     │
│  MEDIUM   → 弹出确认                                     │
│  HIGH     → 拦截，提示手动执行                             │
│  CRITICAL → 拦截，要求审批流程                             │
└─────────────────────────────────────────────────────────┘
  │
  ▼
SSH → 远程服务器
  │
  ▼
审计日志（~/.claude-safe-ops/audit/command_audit.jsonl）
```

### 风险等级

| 等级 | 处理 | 示例 |
|------|------|------|
| **LOW** | 自动放行 | `df -h`、`ps aux`、`uptime`、`docker ps` |
| **MEDIUM** | 弹出确认 | `systemctl restart`、`chmod`、`kubectl apply` |
| **HIGH** | **拦截，提示手动** | `rm -rf`、`kill -9`、`shutdown`、`userdel` |
| **CRITICAL** | **拦截，要求审批** | `DROP DATABASE`、`terraform destroy`、`wipefs` |

原则：**宁可误拦，不可漏放。** 未匹配规则的命令默认 MEDIUM。

### 文件保护（guard-files.sh）

防止 AI 篡改自身的安全控制机制：

| 分区 | 保护对象 | 写入/编辑 | 读取 |
|------|----------|-----------|------|
| **严重** | `.claude/settings.json`、所有 hook 脚本 | **拒绝** | 允许 |
| **敏感** | `credentials.yaml`、`~/.ssh/id_*`、`engine.py`、`.env` | **拒绝** | **需确认** |
| **配置** | `~/.claude-safe-ops/config/*`、`settings.py` | **需确认** | 允许 |
| **普通** | 其他文件 | 允许 | 允许 |

### Hook 完整性校验（validate-hooks.sh）

每个会话首次调用时：
- 验证 4 个 hooks 全部注册在 `.claude/settings.json` 中
- 检查所有 hook 脚本存在且可执行
- 验证 `credentials.yaml` 权限为 600
- 任何安全组件缺失或配置错误时发出警告

### 凭据安全

| 规则 | 实现方式 |
|------|----------|
| 禁止硬编码密码 | 凭据仅通过 getpass 或配置文件获取 |
| 禁止日志泄露密码 | `SensitiveDataFilter` 自动脱敏所有敏感字段 |
| 禁止异常泄露密码 | `SSHConnectionError` 剥离凭据信息 |
| 文件权限管控 | `credentials.yaml` 强制 600 权限 |
| 认证优先级 | 交互输入 > 环境变量 > 配置文件 > SSH Agent |

#### 聊天输入安全

> **绝对不要在 Claude Code 对话中直接输入密码、Token 或密钥。**
>
> 你在对话框中输入的所有内容都会发送到 AI API。如果你说"密码是 abc123"，它会以明文形式传输。

**安全的凭据传递方式：**

| 方式 | 安全？ | 原因 |
|------|--------|------|
| 配置文件（`~/.claude-safe-ops/config/credentials.yaml`） | ✅ | 受 guard-files hook 保护，AI 未经你同意无法读取 |
| SSH 密钥认证 | ✅ | 私钥永远不离开你的机器 |
| SSH Agent | ✅ | 密钥由系统代理管理，对 AI 不可见 |
| `getpass()` 交互式输入 | ✅ | 输入不回显到终端，AI 无法看到 |
| **在对话框输入密码** | ❌ | **以明文发送到 AI API** |
| **`echo $PASSWORD` 命令** | ❌ | **输出对 AI 可见** |

**什么会发送给 AI，什么不会：**

```
┌─────────────────────────────────────────────────┐
│  发送到 AI API（模型可见）                        │
│                                                 │
│  • 你在对话框输入的所有消息                        │
│  • 命令的 stdout/stderr 输出                     │
│  • AI 读取文件时的文件内容                        │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  不会发送（仅保留在本地）                          │
│                                                 │
│  • getpass() 输入（不回显）                       │
│  • SSH 密钥密码（由 ssh-agent 处理）              │
│  • 被 guard-files.sh 拦截的文件                   │
│  • credentials.yaml（SENSITIVE 区，读取需确认）    │
└─────────────────────────────────────────────────┘
```

### 审计追踪

每一次远程操作都记录到 `~/.claude-safe-ops/audit/command_audit.jsonl`：

```json
{
  "timestamp": "2026-04-04T10:30:00+00:00",
  "host": "web-01",
  "command": "systemctl restart nginx",
  "risk_level": "MEDIUM",
  "status": "confirmed",
  "exit_code": 0,
  "operator": "haiqing",
  "matched_rules": ["Restart/reload service"]
}
```

使用 `/audit` 或 `/audit summary` 查看。

### 第三方工具覆盖

风险引擎已覆盖常见 DevOps 工具：

| 工具 | 高危命令示例 | 等级 |
|------|-------------|------|
| Ansible | `ansible all -m shell --limit all` | CRITICAL |
| Terraform | `terraform destroy` | CRITICAL |
| Terraform | `terraform apply` | HIGH |
| Docker | `docker system prune` | HIGH |
| Kubernetes | `kubectl delete --all-namespaces` | CRITICAL |
| Puppet | `puppet cert clean` | HIGH |

## 快捷命令

| 命令 | 用途 |
|------|------|
| `/onboard` | 引导式首次配置（检查安装、依赖、SSH、hooks） |
| `/health` | 健康检查所有服务器 + 本地环境 |
| `/audit` | 审计日志查询（按主机、风险、时间筛选） |
| `/risk <cmd>` | 预评估命令风险（不执行） |
| `/playbook` | 管理和执行运维剧本 |
| `/lang` | 切换 CLI 输出语言 |

## 九大运维模块

| 模块 | 能力 |
|------|------|
| system | 系统信息、CPU/内存/负载、服务管理、用户、crontab |
| network | 接口/路由/DNS、ping/traceroute、端口、防火墙 |
| disk | 磁盘/inode 用量、LVM、SMART 健康、IO 统计、大文件查找 |
| process | 进程排序/搜索/树、kill、lsof、vmstat |
| deploy | 应用状态、文件上传、备份回滚、健康检查 |
| backup | 目录备份、数据库导出(MySQL/PG)、定时备份、清理 |
| security | 端口审计、登录失败、sudo日志、SSH配置、SUID扫描 |
| log | tail/搜索、syslog/dmesg、logrotate、错误统计 |
| playbook | 运维剧本：保存/复用验证过的运维方案 |

## 运维剧本

把验证过的操作保存为剧本，下次直接复用：

```
CsOps> playbook
CsOps/playbook> list
CsOps/playbook> run restart-service service=nginx port=80
CsOps/playbook> save my-check
```

| 剧本 | 用途 |
|------|------|
| restart-service | 服务重启（状态检查 -> 配置验证 -> 重启 -> 验证） |
| disk-cleanup | 磁盘清理（大文件 -> 日志 -> 包缓存 -> 确认释放） |
| high-load-diagnose | 高负载排查（CPU -> 内存 -> IO -> 进程 -> 网络） |
| ssh-bruteforce-check | SSH 暴力破解检测（失败登录 -> IP 统计 -> 安全配置） |
| mysql-slow-query | MySQL 慢查询排查（慢查询 -> 进程 -> 表锁 -> 连接数） |
| **macos-cleanup** | **macOS 系统 & AI 缓存清理**（Claude/ChatGPT/Ollama/HuggingFace + npm/pip/Homebrew/Go + 日志） |

剧本每一步仍经过风险引擎评估 — 安全机制永不绕过。

## 文件隔离

**你的数据和项目代码完全分离** — `git pull` 永远不覆盖你的配置：

```
claude-safe-ops/                          ~/.claude-safe-ops/（你的私有数据）
├── src/          # 代码               ├── config/
├── scripts/      # 安全 hooks         │   ├── hosts.yaml         ← 服务器清单
├── .claude/      # hook 注册          │   ├── credentials.yaml   ← SSH 凭据（600 权限）
│   └── commands/ # 快捷命令           │   └── risk_rules.yaml    ← 自定义规则（可选）
├── install.sh                         ├── playbooks/             ← 用户剧本
└── CLAUDE.md                          ├── audit/                 ← 审计日志
                                       └── session/               ← 当前连接会话
```

## 自定义风险规则

在 `~/.claude-safe-ops/config/risk_rules.yaml` 中添加（覆盖默认规则）：

```yaml
rules:
  - pattern: "\\bmy-critical-app\\b"
    risk_level: HIGH
    description: "涉及核心业务应用"
```

## 语言切换

```bash
export CSOPS_LANG=zh    # 中文
export CSOPS_LANG=ko    # 韩文
export CSOPS_LANG=en    # 英文（默认）
export CSOPS_LANG=auto  # 从系统 locale 自动检测
```

支持：`en`、`zh`、`ko`。添加新语言：复制 `src/config/locales/en.yaml` 为 `{lang}.yaml` 并翻译 — 零代码改动。

Claude Code 模式下，AI 会自动检测你的语言并匹配输出。

## 前置依赖

| 依赖 | 用途 | 必需 |
|------|------|------|
| python3 | CLI 模式 + 精确风险评估 | 推荐（无则 hooks 用 shell 降级） |
| jq | hooks JSON 解析 | 是 |
| paramiko | SSH 连接（pip） | CLI 模式需要 |
| pyyaml | YAML 解析（pip） | 是 |

## 许可证

Apache License 2.0 — 详见 [LICENSE](LICENSE)
