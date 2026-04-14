# SuperWriter - 后端规范

## 架构分层

```
apps/
  server/
    api_server.py        # WSGI 应用入口，路由分发 + 静态文件服务
    pipeline_api.py      # 文件系统闭环 Pipeline API（大纲→章节五层）
core/
  ai/
    provider.py          # OpenAI 兼容 AI 客户端封装
    dialogue.py          # 自然语言对话处理器（意图分类 + 状态机）
    prompts.py           # AI 提示词构建（当前为 stub）
    dialogue_context.py  # 对话上下文管理
  runtime/
    application_services.py  # 服务层 God Object，聚合所有业务逻辑
    storage.py               # 存储层 re-export
    mutation_policy.py       # 变更审批策略引擎（当前为 stub）
    services/                # 拆分出的子服务模块
  storage/
    engine.py            # SQLite 连接管理 + schema 初始化
    _schema.py           # DDL 定义（chat_sessions, ai_provider_config, metadata_markers）
    _chat.py             # 聊天存储 mixin
    _providers.py        # AI 提供者配置存储 mixin
    _metadata.py         # 元数据标记存储 mixin
    _canonical.py        # 规范对象 CRUD
    _derived.py          # 派生制品 CRUD
  skills/
    workshop.py          # 技能校验、适配、diff
  retrieval/             # 检索支持（文档索引 + 一致性检查）
  export/                # 导出投影（文件系统写入计划）
  importers/             # 外部数据导入（fanbianyi、webnovel-writer）
features/
  workspace/service.py   # 工作区管理子服务
  pipeline/service.py    # 流水线生成子服务
```

**每层职责**:
- `apps/server`: 网络层，解析 HTTP 请求、序列化 JSON 响应、服务 SPA 静态文件
- `core/runtime`: 业务逻辑层，编排工作台流程、管理修订和变更策略
- `core/storage`: 持久化层，SQLite CRUD 操作，Mixin 模式组合功能
- `core/ai`: AI 集成层，封装 OpenAI SDK 调用，处理意图分类和对话状态
- `core/skills`: 领域规则层，技能数据校验和格式适配
- `features/`: 按功能域拆分的子服务

## 功能详解

### WSGI 应用（api_server.py）
**做什么**: 接收 HTTP 请求，分发到 API 处理器或返回 SPA 静态文件
**怎么触发**: `waitress` 或其他 WSGI 容器加载 `SuperwriterWSGIApp`
**技术决策**: 使用原生 WSGI 而非 Flask/FastAPI（零框架依赖，但手动解析请求参数、手动构造响应）
**错误处理**:
- `ValueError` → 400/405/409（根据错误消息关键词自动分类：method not allowed → 405, stale/drift → 409）
- `KeyError` → 404
- `sqlite3.Error` → 502（打印 traceback 后返回 dependency_failure）
- 所有异常 → 500（兜底）

### 五层流水线 Pipeline API（pipeline_api.py）
**做什么**: 基于文件系统管理大纲→剧情→事件→场景→章节的五层节点树
**怎么触发**: HTTP 请求到 `/api/pipeline/*` 路径
**技术决策**: 节点用 `{layer}-{coord1}-{coord2}.txt` 命名存储在文件系统上（直观可调试，但 rename/move 需要级联更新所有子节点文件名）
**节点地址**: `NodeAddress` 对象封装层级名和坐标元组，如 `plot-1-2` 表示第 1 个大纲下的第 2 个剧情节点
**AI 扩写**: `expand_node()` 调用 AI `generate_structured()` 返回 JSON 数组，每个元素是一个子节点的文本内容
**SSE 推送**: 使用 `watchdog` 库监听 `nodes/` 目录变化，通过 `queue.Queue` 广播到所有 SSE 订阅者（慢消费者丢弃事件）
**RAG 索引**: 基于关键词的简单全文搜索，扫描前四层 txt 文件建立内存索引并持久化到 `rag_index.json`

### 规范对象工作台（application_services.py）
**做什么**: 编排从大纲到章节的 AI 生成流程，管理对象的修订链和变更审批
**怎么触发**: API 路由调用 `SuperwriterApplicationService` 上的方法
**技术决策**: 采用 God Object + 内部委托模式，12 个子服务通过回调函数注入互相引用（避免循环依赖，但回调链复杂难追踪）
**修订漂移检查**: 更新操作必须携带 `base_revision_id`/`expected_parent_revision_id`，与当前 head 不匹配则拒绝（乐观并发控制）
**生成流程**: 每个工作台（outline_to_plot/plot_to_event/event_to_scene/scene_to_chapter）遵循相同模式:
1. 读取并校验上游对象
2. 收集上下文（小说信息、技能、角色、场景设定）
3. 调用 AI 生成结构化 JSON
4. AI 失败时降级为简单字段复制
5. 创建路径 → 直接写入新对象；更新路径 → 经过变更策略引擎

### AI 提供者管理
**做什么**: CRUD AI 提供者配置（base_url、api_key、model_name 等），支持多个提供者、激活切换、连接测试
**怎么触发**: `/api/providers` 或 `/api/settings` 路由的 GET/POST
**技术决策**: 使用 OpenAI Python SDK 的 `OpenAI(base_url=...)` 方式对接所有兼容 API（一套代码兼容多家，但不支持非 OpenAI 格式的 AI 服务如 Anthropic 原生 API）
**连接测试**: 发送 "Respond with exactly: OK" 测试消息，检查响应是否包含 "OK"，记录延迟毫秒数

### 对话处理器（dialogue.py）
**做什么**: 解析用户自然语言消息，分类意图，路由到对应工作台操作
**怎么触发**: 聊天 API 接收用户消息后调用 `DialogueProcessor.process_turn()`
**技术决策**: 双模式意图分类——有 AI 时调用模型分类，无 AI 时使用中英文关键词匹配（保证无 AI 也能基本工作）
**状态机**: `DialogueStateMachine` 管理会话状态流转：IDLE → AWAITING_CONTEXT → PROCESSING → COMPLETED → IDLE
**支持的意图**: 工作台操作（4 种层级转换）、审核操作、查询操作、技能操作、内容编辑、通用聊天、帮助

### 技能工坊（workshop.py）
**做什么**: 校验、适配、比对作者控制技能的 payload
**怎么触发**: 创建/更新/导入技能时调用
**技术决策**: 受约束技能模型——白名单字段 + 黑名单字段 + 类型特定校验（严格控制技能能做什么，防止注入 generation_params/tool_permissions 等危险字段）
**支持的技能类型**: style_rule（风格规则）、character_voice（角色语音）、narrative_mode（叙事模式）、pacing_rule（节奏规则）、dialogue_style（对话风格）
**导入适配器**: 支持 3 种外部格式：prompt_template、custom_agent、ai_role，自动映射字段到受约束技能格式

### SQLite 存储引擎（engine.py + _schema.py）
**做什么**: 管理数据库连接、初始化表结构
**技术决策**: 使用 Mixin 模式组合 `_ChatMixin` + `_ProvidersMixin` + `_MetadataMixin` 到 `CanonicalStorage`（复用灵活，但多继承 MRO 可能产生意外行为）
**Schema**: 4 张核心表——chat_sessions、chat_message_links、ai_provider_config、metadata_markers（另有 canonical_objects/canonical_revisions/derived_records 等表在其他 mixin 中定义）
**外键约束**: `PRAGMA foreign_keys = ON`（每次连接时设置，确保引用完整性）

## API 端点

| 路径 | 方法 | 用途 |
|------|------|------|
| `/api/startup` | GET | 获取所有工作区上下文列表（项目+小说） |
| `/api/create-novel` | POST | 创建新项目+小说，在本地文件夹生成 `.superwriter/workspace.json` |
| `/api/skills` | GET | 获取技能工坊快照（技能列表、选中技能、版本历史、diff） |
| `/api/skills` | POST | 技能 CRUD（action: create/update/toggle/rollback/import） |
| `/api/providers` `/api/settings` | GET | 获取 AI 提供者配置列表 |
| `/api/providers` `/api/settings` | POST | 提供者 CRUD（action: save/activate/delete/test） |
| `/api/pipeline/nodes` | GET | 列出指定层级的文件系统节点 |
| `/api/pipeline/nodes/{addr}` | GET/PUT/DELETE | 读取/写入/删除单个文件节点 |
| `/api/pipeline/nodes/{addr}/expand` | POST | AI 扩写：从父节点生成子节点 |
| `/api/pipeline/chat` | POST | 文件节点对话台（基于节点内容的多轮对话） |
| `/api/pipeline/rag/rebuild` | POST | 重建 RAG 关键词索引 |
| `/api/pipeline/rag/search` | POST | 关键词搜索节点内容 |
| `/api/pipeline/events` | GET | SSE 事件流，推送文件变化通知 |

## 数据模型

### canonical_objects（规范对象）
存储项目中所有结构化对象（project/novel/outline_node/plot_node/event/scene/skill 等），每个对象有 family + object_id 唯一标识。

### canonical_revisions（修订历史）
每次变更创建新 revision，形成链式历史。`parent_revision_id` 指向前一个版本，`snapshot` 存储完整 payload 快照。

### derived_records（派生制品）
chapter_artifact 和 export_artifact 存储在此表。与 canonical_objects 不同，派生制品不走修订链，每次生成创建新记录。

### ai_provider_config
| 字段 | 类型 | 说明 |
|------|------|------|
| provider_id | TEXT PK | UUID |
| provider_name | TEXT | 提供者标识（openai/azure/local/custom） |
| base_url | TEXT | API 基础 URL |
| api_key | TEXT | 明文存储的 API 密钥 |
| model_name | TEXT | 模型名称 |
| temperature | REAL | 0-2，默认 0.7 |
| max_tokens | INTEGER | >0，默认 4096 |
| is_active | INTEGER | 0 或 1，同时只能有一个激活 |

### 文件系统节点（Pipeline）
```
.superwriter/nodes/
  outline-1.txt          # 第 1 个大纲
  plot-1-1.txt           # 大纲 1 的第 1 个剧情
  plot-1-2.txt           # 大纲 1 的第 2 个剧情
  event-1-1-1.txt        # 剧情 1-1 的第 1 个事件
  scene-1-1-1-1.txt      # 事件 1-1-1 的第 1 个场景
  chapters/
    chapter-1-1-1-1-1.txt  # 场景的章节正文
```
