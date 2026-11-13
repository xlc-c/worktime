# 多端同步（Sync）

**默认关闭，逐通道选择。** 有些数据适合跨设备（时间段、应用名、事项），有些不适合（焦点文本、
剪贴板、网页正文、窗口标题里的客户名）。WorkTime 不替你决定，也不上传任何东西：
同步包写到**你自己选的文件夹**（OneDrive、坚果云、NAS、U 盘），要不要加密由你定。

## 三个原则

1. **显式开启**：`sync.enabled = false` 时，任何同步命令都会拒绝执行。
2. **逐通道**：`sync.channels` 里每个数据类一个开关，只有勾选的字段会写进同步包。
3. **只读外来数据**：导入的日期进 `foreign_days` 表，与本地 `segments` 完全隔离；报表在
   同步开启时才合并展示，误导入不会污染本机时间线。

## 通道

| 通道 | 默认 | 内容 | 风险 |
| --- | --- | --- | --- |
| `times` | 开 | 起止时间、时长、应用名 | 必需，关不掉 |
| `matters` | 开 | 事项 / 任务名称、费率 | 客户名会暴露给对端设备 |
| `window_titles` | 关 | 窗口标题 | 文件名里的客户/项目名 |
| `urls` | 关 | 网址、页面标题 | 内网地址、搜索词 |
| `page_text` | 关 | 网页正文 | 最敏感 |
| `focused_text` | 关 | 焦点输入框文本 | Excel 单元格、邮件正文 |
| `clipboard` | 关 | 剪贴板预览（前 240 字） | 复制过的敏感片段 |

关掉通道时字段会被**删除**，不是置空后再发；`evidence` 也会重建成只含应用名。

## 用法

```bat
:: 看看会同步什么（不写文件）
wt sync preview --days 7

:: 导出到指定目录（可选口令加密）
wt sync export --days 7 --out D:\WorkTimeSync
set WT_SYNC_PASSPHRASE=你的口令
wt sync push            :: 导出到 config.json 里的 sync.folder

:: 从文件夹导入所有未导入过的包（按 SHA-256 去重）
wt sync pull
```

复核页：`⚙ 设置 → 多端同步`，勾通道 → 保存 → 「预览会同步什么」→「导出/导入」。

## 加密

`sync.encrypt = true` 时用口令加密（也可以每次在界面上临时输入）：

- KDF：scrypt（Windows CPython 自带），环境缺少 scrypt 时自动降级为 PBKDF2-HMAC-SHA256 12 万轮
- 加密：ChaCha20（RFC 7539），96-bit nonce
- 完整性：HMAC-SHA256（encrypt-then-MAC），先验签再解密
- 文件头 `WTB1` + KDF id，所以两种 KDF 互相兼容

口令**不写进 config.json**；可用环境变量 `WT_SYNC_PASSPHRASE`，或每次在界面输入。
同步包（`.wtb`）是明文 JSON 或上述加密信封，导入前可以直接打开看。

## 冲突与去重

- 同一 `(device_id, date)` 重复导入会覆盖那台设备那天的版本（不会产生重复）。
- 同一个文件（SHA-256 相同）只会导入一次，`sync_files` 表记录已导入的包。
- 事项费率：只导入本地没有的路径，不会静默覆盖你本机设置的单价。
- 自己的包会被识别并跳过（`own bundle`）。

## 企业环境

- 如果把 `sync.folder` 指向公司网盘，等于把选中的通道交给公司留存——请先确认合规。
- 需要“完全不允许内容离开本机”时：保持 `sync.enabled = false`，或只开 `times` + `matters`。
- `policy.locked = true` 用于锁定采集范围；同步开关同理建议由管理员在 `config.json` 里固定。
