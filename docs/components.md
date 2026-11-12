# 组件与许可证清单（SBOM 摘要）

WorkTime v0.1.0。除下列组件外，剩余代码为本项目原创（MIT）。

## 运行时（随便携包分发）

| 组件 | 版本 | 许可证 | 说明 |
|---|---|---|---|
| CPython | 3.10–3.12 | PSF-2.0 | 便携包内 `runtime/`，仅使用标准库 |
| Python 标准库 | 同 CPython | PSF-2.0 | `sqlite3`、`ctypes`、`http.server`、`urllib` 等 |

**核心功能不依赖任何第三方 Python 包**（无 numpy/scipy/requests/pywin32）。

## 可选组件（不装也能运行）

| 组件 | 用途 | 许可证 | 备注 |
|---|---|---|---|
| openpyxl | 生成 XLSX 报表 | MIT | 缺失时自动只输出 Markdown/CSV |
| et_xmlfile | openpyxl 依赖 | MIT | 纯 Python |
| uiautomation | 读取焦点控件文本 | Apache-2.0 | **已随便携包附带**，失败时自动禁用 |
| comtypes | uiautomation 依赖 | MIT | **已随便携包附带**，纯 Python（ctypes） |
| llama.cpp (`llama-server.exe`) | 本地 LLM 推理 | MIT | 可选，CPU 版，仅监听 127.0.0.1 |
| Qwen3-4B GGUF | 本地命名模型 | Apache-2.0 | 可选，约 2.5GB，需自行下载 |

## 浏览器扩展

- 自有代码（MIT），无第三方库；
- Manifest V3，Chrome / Edge 通用；
- 权限：`storage`（保存 token/端口/黑名单）、`tabs`（读取活动标签页 URL/标题）、
  `alarms`（保活），以及 `http://127.0.0.1/*` 主机权限；
- 内容脚本仅在 `http/https` 页面、顶层框架运行，标签页隐藏时不上报。

## 网络依赖

运行期**无网络请求**，仅本机回环：`127.0.0.1:18731`（采集接收）、
`127.0.0.1:18732`（复核页）、可选 `127.0.0.1:8080`（本地 LLM）。

## 构建与校验

- 便携包由 `scripts/package-portable.ps1` 从本机 Python 运行时生成；
- 交付时对 zip 计算 SHA-256（Windows：`Get-FileHash .\WorkTime.zip -Algorithm SHA256`），
  与 `docs/IT-审批材料.md` 中的记录比对后再解压。
