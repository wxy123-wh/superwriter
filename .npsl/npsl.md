# SuperWriter - NPSL 规范
# 生成日期: 2026/04/16

---

## 项目概览

做什么: 面向小说作者的桌面写作工具，提供文件编辑、角色/地点/时间线管理、章节一致性校验、伏笔追踪、AI 写作技能版本化管理和 AI 对话辅助
面向谁: 需要管理长篇小说世界观和写作一致性的中文/英文小说作者

---

## 技术选择（看界面看不出来的决策）

### 运行时

- Electron 35 桌面应用（用户数据存在 `userData` 目录下，不依赖云服务，完全离线可用）
- 前后端通过 Electron IPC 通信，不走 HTTP（省去了服务端口占用和 CORS 配置，但前端代码必须通过 `window.electronAPI.invoke()` 调用后端）
- pnpm monorepo 管理三个包：`apps/server`（Electron 主进程）、`apps/frontend`（渲染进程）、`packages/shared`（共享类型）

### 存储

- better-sqlite3 单文件数据库 `superwriter.db`（项目、小说、技能、AI 配置、聊天历史全部存在同一个 .db 文件里，换机器只需拷贝一个文件，但不支持多实例同时写入）
- WAL 模式开启（读写并发性能更好，但会产生 .db-shm 和 .db-wal 附属文件）
- 小说世界观数据（manifest、foreshadow、snapshot）存储为工作目录下的 JSON 文件（`.superwriter/` 目录），不在 SQLite 中（用户可以用 Git 管理这些 JSON 文件的版本）
- AI 提供商的 API 密钥明文存储在 SQLite 的 `ai_provider_config` 表中（泄露风险，生产环境需加密）

### 认证/安全

- 无用户认证系统（单用户桌面应用，所有操作默认以 `'user'` 身份记录）
- 文件路径使用 `safeJoin()` 做目录遍历防护（`path.resolve` 后检查前缀是否在 base 目录内）
- Electron 启用 `contextIsolation: true` + `nodeIntegration: false`（渲染进程无法直接访问 Node API，必须通过 preload 暴露的 IPC 桥接）

### 架构

- 前端 SPA + 后端 Electron 主进程（类 VS Code 布局：TitleBar + ActivityBar + FileTree 侧边栏 + 主内容区 + StatusBar）
- 前端使用 React Router 做视图切换，但所有视图嵌套在同一个 `AppShell` 布局组件内（切换视图不会重置文件树和编辑器状态）
- 数据库 schema 在 `getDb()` 首次调用时自动创建（`CREATE TABLE IF NOT EXISTS`），无迁移工具（schema 变更需要手动处理兼容性）

---

## 核心流程

### 1. 启动流程
1. Electron 主进程启动 → 创建 BrowserWindow
2. 开发模式加载 `localhost:5173`，生产模式加载打包后的 `index.html`
3. 主进程调用 `getDb()` → 懒初始化 SQLite + 自动建表
4. 前端通过 `getStartup` IPC 获取已有的 project/novel 列表
5. 用户选择已有工作区 或 通过 `openDirectory` 对话框打开本地文件夹

### 2. 文件编辑流程
1. 用户从 FileTree 选择文件 → IPC `readLocalFile` 读取内容
2. Monaco Editor 显示文件内容（根据扩展名自动选择语言高亮）
3. 编辑后标记 `isDirty` → 保存时 IPC `saveLocalFile` 写回磁盘

### 3. 世界观管理流程
1. 用户通过 ManifestView 添加/编辑角色、地点、时间线事件、追踪物品
2. 数据以 JSON 文件形式存储在工作目录的 `.superwriter/manifest.json`
3. 每次操作都是 load → modify → save 全量覆盖（无增量更新，并发安全性依赖单用户假设）

### 4. 一致性校验流程
1. 用户在 ConsistencyView 触发 `extractChapterContent` → 正则提取角色、地点、时间标记
2. 提取结果保存为章节快照 `.superwriter/state-snapshots/chapter-NNN.json`
3. `checkConsistency` 对比快照与 manifest → 发现角色状态冲突（如死人复活）、秘密遗漏等

### 5. AI 对话流程
1. 用户在 ChatPanel 发送消息 → IPC `sendChat`
2. 主进程从 SQLite 取激活的 AI provider 配置
3. 调用 OpenAI 兼容格式的 `/chat/completions` API
4. 响应存入 `chat_message_links` 表 → 返回前端显示

---

## 领域对象

| 对象 | 用途 | 特别说明 |
|------|------|----------|
| Project | 顶层组织单元，包含一个或多个 Novel | ID 格式 `proj_xxxxxxxx`，存 SQLite |
| Novel | 一部小说，属于某个 Project | ID 格式 `nov_xxxxxxxx`，存 SQLite |
| NovelManifest | 小说世界观：角色、地点、时间线、追踪物品 | 存 JSON 文件（`.superwriter/manifest.json`），不在 SQLite |
| Character | 角色，含别名、外貌、性格、关系网络 | 关系支持 7 种类型 × 3 种强度，删除时级联清理关系引用 |
| Foreshadow | 伏笔，含埋设章节和解决章节 | 状态三态：pending / resolved / abandoned，存 JSON 文件 |
| ChapterSnapshot | 章节状态快照：每个角色位置/情绪/生死状态、世界状态 | 存文件系统 `.superwriter/state-snapshots/`，按章节号命名 |
| SkillObject + SkillRevision | AI 写作技能的版本化管理 | 技能支持创建、更新（新建 revision）、回滚、导入，存 SQLite |
| AIProviderConfig | AI 服务商配置：URL、密钥、模型、温度 | 同时只能有一个 active provider，切换时先全部停用再激活目标 |
| ChatSession + ChatMessageLink | 聊天会话和消息 | 消息 payload 为 JSON 存储，支持关联到特定 skill revision |

---

## 已知限制

- manifest 操作每次全量 load + save JSON 文件，不适用于超大 manifest（数百角色场景）
- content-extractor 使用简单正则提取角色名和地点（中文人名靠字符数 2-4，英文靠首字母大写），误报率高
- 无多窗口支持，`mainWindow` 是全局单例
- 技能版本比较（`SkillWorkshopComparison`）在类型中定义了但服务端未实现对比逻辑
- AI 聊天不支持上下文连续对话（每次只发送单条用户消息，不带历史）
- `chat_sessions` 表的 INSERT 语句中 `created_by` 字段重复出现，可能导致 SQL 报错
- `preload.ts` 是死文件（静态分析检测到但未被正确引用）
- API 密钥明文存储在 SQLite 中，无加密
- `readLocalFile`/`saveLocalFile` 未做 `safeJoin` 路径检查，存在路径遍历风险
