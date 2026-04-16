# SuperWriter - 后端规范

## 架构分层

```
apps/server/src/
├── main.ts              # Electron 主进程入口 + 30 个 IPC handler（649 行，职责过多）
├── db.ts                # SQLite 数据库管理（单例 + schema 初始化，7 张表）
├── preload.ts           # Electron preload 脚本（死文件，当前未被正确引用）
├── repositories/
│   ├── manifest-repository.ts    # 小说世界观 JSON 文件读写（245 行，19 个导出）
│   ├── foreshadow-repository.ts  # 伏笔 JSON 文件读写（内存缓存 + 文件持久化）
│   └── snapshot-repository.ts    # 章节快照 JSON 文件读写（按章节号分文件存储）
└── services/
    └── content-extractor.ts      # 章节内容正则提取器（角色名、地点、时间标记、物品）

packages/shared/src/
├── api-contract.ts      # API 响应信封：apiOk() / apiErr()
├── index.ts             # 统一导出
└── types/
    ├── json.ts           # JSON 基础类型（JSONObject / JSONValue）
    ├── chat.types.ts     # 聊天相关类型
    ├── skill.types.ts    # 技能工坊请求/响应/结果类型（132 行完整定义）
    └── workbench.types.ts # 工作台类型
```

## 功能详解

### 数据库管理（db.ts）

**做什么**: 提供全局 SQLite 数据库实例，首次调用时自动创建所有表
**怎么触发**: 任何需要数据库的 IPC handler 调用 `getDb()`
**技术决策**:
- 使用 better-sqlite3 同步 API（比 node-sqlite3 快，不需要回调，但阻塞事件循环）
- 数据库文件路径硬编码为 `__dirname/../../../superwriter.db`（相对于编译输出目录，生产环境路径可能不对）
- 7 张表在一个函数里全部 `CREATE TABLE IF NOT EXISTS`（无版本号、无迁移系统）
- 3 个索引自动创建：`novels.project_id`、`skill_objects.(project_id, novel_id)`、`skill_revisions.object_id`
**错误处理**: 数据库打开失败会抛异常中断启动，无重试

### 工作区管理

**做什么**: 管理用户的小说项目和工作目录
**怎么触发**: 应用启动时 `getStartup`，用户创建/打开工作区时
**技术决策**:
- 工作区根目录 `workspaceRoot` 存在 IPC handler 闭包内的局部变量中（非持久化，重启应用后丢失）
- 项目/小说 ID 使用 `uuid` 生成并截断为 8 位（`proj_xxxxxxxx`、`nov_xxxxxxxx`），碰撞概率极低但非零
- `getStartup` 通过 JOIN projects + novels 返回所有 workspace 上下文
**错误处理**: `workspaceRoot` 为空时返回空数组或错误消息，不抛异常

### 文件系统操作

**做什么**: 读写用户本地文件系统上的文件和目录
**怎么触发**: 前端文件树展开/选择文件/保存文件
**技术决策**:
- 提供两套文件 API：
  - `readDirectory`/`readFile`：基于 `novels/{novelId}/` 目录（userData 内的受管目录，使用 `safeJoin` 防护）
  - `readLocalDirectory`/`readLocalFile`/`saveLocalFile`/`createLocalFile`：基于用户选择的任意本地目录（**未做 safeJoin 路径检查**）
- 隐藏文件自动过滤（`.` 开头的文件/目录不显示）
- 目录排序：目录在前、文件在后，字母序
- 文件内容统一使用 `utf-8` 编码读写（不支持二进制文件）
**错误处理**: `ENOENT` 返回空内容/空列表，其他错误向上抛

### 小说世界观（manifest-repository.ts）

**做什么**: 管理角色、地点、时间线事件、追踪物品的 CRUD 操作
**怎么触发**: 前端 ManifestView 中的添加/编辑/删除操作 → IPC `loadNovelManifest`/`saveNovelManifest`
**技术决策**:
- 数据存储为 `.superwriter/manifest.json` 单个 JSON 文件（全量读写，每次操作都 load → modify → save）
- 角色关系（`CharacterRelationship`）支持 7 种关系类型（family/friend/enemy/lover/mentor/rival/stranger）和 3 种强度等级（strong/medium/weak）
- 删除角色时级联删除其他角色对该角色的关系引用
- 类型定义在 server 端重复定义了一份（注释 "to avoid cross-module imports"），与前端 `types/novel-manifest.ts` 不共享
- 所有 CRUD 函数都是独立导出的（非 class），但通过 `import *` 使用
**错误处理**: 文件不存在时返回空 manifest（`createEmptyManifest()`），其他 IO 错误向上抛

### 伏笔系统（foreshadow-repository.ts）

**做什么**: 管理伏笔的创建、更新、解决、删除
**怎么触发**: 前端 ForeshadowView → IPC `loadForeshadows`/`saveForeshadows`
**技术决策**:
- 使用 class 实例化（`new ForeshadowRepository()`），内存中维护 `foreshadows[]` 数组
- 需要显式 `load()`/`save()` 同步到文件（内存操作不会自动持久化）
- IPC handler 中直接修改 `foreshadowRepo['foreshadows']` 私有属性（绕过了类的封装）
- 伏笔三状态机：`pending` → `resolved`（指定解决章节）或 `abandoned`
- 支持按章节查询 `getByChapter()` 和获取所有未解决 `getPending()`
**错误处理**: 文件不存在时初始化为空数组

### 章节快照（snapshot-repository.ts）

**做什么**: 按章节存储角色状态和世界状态的快照
**怎么触发**: 前端 ConsistencyView → IPC `loadChapterSnapshot`/`saveChapterSnapshot`/`getAllSnapshots`
**技术决策**:
- 每章一个 JSON 文件，文件名格式 `chapter-001.json`（3 位数字零填充）
- 快照数据结构：`CharacterState[]`（角色位置/情绪/生死/近期事件）+ `WorldState`（时间线/冲突/秘密/谜团数）
- `getLatest()` 遍历目录找最大章节号（O(n) 文件读取，章节多时慢）
- `getAll()` 一次性读取所有快照文件并按章节号排序（无分页，章节多时内存占用大）
**错误处理**: 文件/目录不存在返回 null 或空数组

### 内容提取器（content-extractor.ts）

**做什么**: 从章节文本中用正则提取角色名、地点、时间标记、物品提及
**怎么触发**: IPC `extractChapterContent`
**技术决策**:
- 纯正则/字符串匹配，无 NLP 或 AI 辅助（速度快但准确率低）
- 中文人名：匹配 2-4 个连续汉字/大写字母（误报率极高）
- 英文人名：首字母大写的单词组合（最多 3 个词）
- 地点：30 个中文 + 30 个英文预定义地点词 + "在X"/"来到X" 等动词前缀模式
- 时间标记：10 组中英文日期/时间/星期正则模式
- 物品：中英文常见武器/物品关键词 + "took/grabbed" 等动词模式
**错误处理**: 正则不匹配返回空数组，不会抛异常

### 技能工坊

**做什么**: 管理 AI 写作技能（如"写打斗场景"、"写内心独白"）的版本化 CRUD
**怎么触发**: 前端 SkillsView → IPC `getSkills`/`upsertSkill`/`rollbackSkill`/`importSkill`
**技术决策**:
- 双表设计：`skill_objects`（技能元数据）+ `skill_revisions`（版本历史）
- 每次更新创建新 revision，不修改旧版本（append-only，支持完整历史回溯）
- 回滚 = 复制目标 revision 的内容创建一个新 revision（不是指针回退，保留完整审计链）
- `source_kind` 区分 `manual`（手动创建）和 `imported`（导入）
- `is_active` 控制技能是否启用
- `getSkills` 使用 `GROUP BY o.object_id` 获取每个技能的最新 revision（但不带 ORDER BY，可能不总是返回最新）
**错误处理**: revision 不存在时返回 `{ success: false, error: 'Revision not found' }`

### AI 聊天

**做什么**: 将用户消息发送给 AI 并返回响应
**怎么触发**: 前端 ChatPanel → IPC `sendChat`
**技术决策**:
- 使用原生 `fetch()` 调用 OpenAI 兼容的 `/chat/completions` 端点（不依赖 OpenAI SDK，支持任何兼容服务）
- 不发送历史消息，每次只发一条 user message（无上下文连续对话）
- AI 响应同步存入 SQLite `chat_message_links` 表（聊天记录持久化）
- `chat_sessions` 表 INSERT 语句中 `created_by` 字段出现两次（SQL 错误隐患）
**错误处理**: API 调用失败返回错误消息字符串（不抛异常），无 provider 时返回提示文案

### AI 提供商管理

**做什么**: 配置和管理 AI 服务提供商（支持多个，但同时只激活一个）
**怎么触发**: 前端设置界面 → IPC `getSettings`/`saveProvider`/`activateProvider`/`deleteProvider`/`testProvider`
**技术决策**:
- 支持 CRUD + 激活切换 + 连通性测试（测试通过访问 `/models` 端点检查 HTTP 状态码）
- 激活逻辑：先 `UPDATE SET is_active = 0`（全部停用），再 `SET is_active = 1`（激活目标），非原子操作
- 默认 temperature 0.7、max_tokens 4096
- `saveProvider` 支持 upsert（检测 provider_id 是否已存在，存在则 UPDATE，不存在则 INSERT）
**错误处理**: provider 不存在时返回 `{ success: false, error: 'Provider not found' }`

## IPC 端点清单

| 端点名 | 读/写 | 用途 |
|--------|-------|------|
| `ping` | 读 | 连通性检查（返回 'pong'） |
| `openDirectory` | 读 | 打开文件夹选择对话框 |
| `setWorkspaceRoot` | 写 | 设置工作目录根路径 |
| `readLocalDirectory` | 读 | 读取本地目录列表 |
| `readLocalFile` | 读 | 读取本地文件内容 |
| `saveLocalFile` | 写 | 保存本地文件 |
| `createLocalFile` | 写 | 创建空文件 |
| `getStartup` | 读 | 获取启动数据（项目和小说列表） |
| `createWorkspace` | 写 | 创建新工作区（项目 + 小说） |
| `readDirectory` | 读 | 读取受管小说目录 |
| `readFile` | 读 | 读取受管小说文件 |
| `getSkills` | 读 | 获取技能列表（含最新 revision） |
| `upsertSkill` | 写 | 创建/更新技能（新建 revision） |
| `rollbackSkill` | 写 | 回滚技能版本（复制目标 revision） |
| `importSkill` | 写 | 导入外部技能 |
| `getSettings` | 读 | 获取 AI 提供商配置列表 |
| `saveProvider` | 写 | 创建/更新提供商配置 |
| `activateProvider` | 写 | 激活指定提供商（停用其他） |
| `deleteProvider` | 写 | 删除提供商 |
| `testProvider` | 读 | 测试提供商连通性 |
| `sendChat` | 写 | 发送聊天消息并获取 AI 响应 |
| `loadForeshadows` | 读 | 加载伏笔列表 |
| `saveForeshadows` | 写 | 保存伏笔列表 |
| `ensureManifestDir` | 写 | 确保 .superwriter 目录存在 |
| `loadNovelManifest` | 读 | 加载小说世界观 |
| `saveNovelManifest` | 写 | 保存小说世界观 |
| `loadChapterSnapshot` | 读 | 加载指定章节快照 |
| `saveChapterSnapshot` | 写 | 保存章节快照 |
| `getAllSnapshots` | 读 | 获取所有章节快照（按章节号排序） |
| `extractChapterContent` | 读 | 正则提取章节内容元素 |

## 数据模型

### SQLite 表结构

| 表名 | 主键 | 用途 | 关键字段 |
|------|------|------|----------|
| `projects` | `project_id` TEXT | 项目 | title, created_at, updated_at |
| `novels` | `novel_id` TEXT | 小说（FK → projects） | project_id, novel_title |
| `skill_objects` | `object_id` TEXT | 技能对象 | project_id, novel_id, name, source_kind, donor_kind |
| `skill_revisions` | `revision_id` TEXT | 技能版本（FK → skill_objects） | object_id, revision_number, instruction, is_active |
| `ai_provider_config` | `provider_id` TEXT | AI 服务商配置 | base_url, api_key(明文), model_name, temperature, is_active |
| `chat_sessions` | `session_state_id` TEXT | 聊天会话 | project_id, novel_id, runtime_origin |
| `chat_message_links` | `message_state_id` TEXT | 聊天消息（FK → chat_sessions） | chat_role, payload_json |

### 文件系统数据

| 路径 | 格式 | 用途 |
|------|------|------|
| `{workspace}/.superwriter/manifest.json` | JSON | 小说世界观（角色、地点、时间线、物品） |
| `{workspace}/.superwriter/foreshadows.json` | JSON | 伏笔列表 |
| `{workspace}/.superwriter/state-snapshots/chapter-NNN.json` | JSON | 章节状态快照（每章一文件） |
