# SuperWriter - NPSL 规范
# 生成日期: 2026/04/15

---

## 项目概览

做什么: AI 辅助小说创作工具，通过五层流水线（大纲→剧情→事件→场景→章节）将结构化大纲逐步扩展为可发布的章节正文
面向谁: 网文作者、小说创作者

---

## 技术选择（看界面看不出来的决策）

### 存储
- 使用 SQLite 单文件数据库存储规范对象和修订历史（换机器只需拷贝一个 db 文件，但不支持并发写入）
- 规范对象采用 append-only 修订链：每次变更创建新 revision，旧数据永不覆盖（支持回滚，但数据库体积会持续增长）
- 同时存在文件系统存储层（`.superwriter/nodes/` 下的 txt 文件），Pipeline API 直接读写文件而非数据库（两套存储并行，数据一致性依赖调用方）

### 认证/安全
- 无用户认证机制，单用户本地运行（不适用于多用户或公网部署）
- AI 提供者的 API 密钥明文存储在 SQLite `ai_provider_config` 表中（泄露风险，生产环境需加密）
- 前端展示 API 密钥时做掩码处理（首尾各露 2 位，中间用 `*` 替代），但后端 API 响应中已剥除原始密钥

### 架构
- 前后端分离：Python WSGI 后端 + React SPA 前端，后端同时承担静态文件服务（开发简单，但 WSGI 同步模型不适合高并发）
- 服务层采用 God Object 模式：`SuperwriterApplicationService` 聚合所有业务逻辑，通过内部委托拆分为 12 个子服务（入口统一，但类依然庞大）
- 前后端契约通过手写 parser 函数严格校验每个 API 响应字段（无 codegen，前后端修改需手动同步）

### AI 集成
- 使用 OpenAI Python SDK 对接 AI（不限于 OpenAI，任何 OpenAI 兼容 API 均可使用，如本地 Ollama、Azure）
- AI 生成采用结构化 JSON 输出模式（`response_format: json_object`）解析生成结果（依赖模型支持 JSON mode，不兼容的模型会失败）
- AI 不可用时所有工作台操作降级为简单复制（不阻塞工作流，但生成质量降为零）

---

## 核心流程

### 五层生产流水线
```
大纲(outline_node)
  → 剧情(plot_node)     # AI 将大纲拆解为多个剧情节点
    → 事件(event)        # AI 将剧情分解为具体事件
      → 场景(scene)      # AI 将事件展开为带 POV、角色、节拍的场景
        → 章节(chapter)  # AI 将场景写成散文正文
          → 导出(export) # 投影为文件系统上的可发布文件
```

每一步支持：
1. **创建模式**：从上游对象生成新的下游对象
2. **更新模式**：基于上游变更刷新已有下游对象，经过修订漂移检查
3. **迭代模式**：生成多个候选方案，用户反馈后 AI 修订，最终选定一个

### 变更审批流
```
变更请求 → MutationPolicyEngine 判定
  → auto_applied（安全变更，直接写入）
  → review_required（风险变更，进入审核台等待人工批准）
```
注：当前 mutation_policy.py 为 stub 实现，核心编辑策略已移除

### 技能工坊
作者可创建/导入/编辑"受约束技能"（如风格规则、角色语音、叙事模式），附加到小说后影响后续 AI 生成行为。技能有版本历史，支持回滚和 diff 对比。

---

## 领域对象

| 对象 | 用途 | 特别说明 |
|------|------|----------|
| project | 顶层容器，一个项目可包含多部小说 | 与本地文件夹绑定，`.superwriter/workspace.json` 记录映射 |
| novel | 小说实体，挂载在 project 下 | 所有下游对象通过 `novel_id` 关联 |
| outline_node | 大纲节点，用户手动导入 | 支持层级（parent_outline_node_id），但 UI 目前只用单层 |
| plot_node | 剧情节点，由大纲 AI 生成 | 一个大纲可生成多个剧情节点 |
| event | 具体事件，由剧情 AI 生成 | 包含地点、涉及角色等结构化字段 |
| scene | 详细场景，由事件 AI 生成 | 包含 POV 角色、在场角色列表、节拍拆解 |
| chapter_artifact | 章节制品（派生对象），由场景 AI 生成 | 存储在 derived_records 表，非 canonical 对象 |
| export_artifact | 导出制品（派生对象） | 文件系统投影的元数据记录 |
| skill | 作者控制技能 | 5 种类型：style_rule/character_voice/narrative_mode/pacing_rule/dialogue_style |
| chat_session | 对话会话 | 支持多轮对话，AI 可在对话中触发工作台操作 |

---

## 双存储架构

系统同时运行两套存储：

1. **CanonicalStorage（SQLite）**：存储规范对象修订链、聊天记录、AI 提供者配置、元数据标记（`SuperwriterApplicationService` 使用）
2. **FileStore（文件系统）**：以 `大纲-1.txt`、`剧情-1-1.txt` 等命名的 txt 文件，通过 `PipelineAPI` 直接 CRUD（`FileWatcher` + watchdog 监听变更并通过 SSE 推送到前端）

两套存储互不感知，PipelineAPI 中的对话台和 AI 扩写直接操作文件，不经过 CanonicalStorage 的修订链。

---

## 已知限制

- `SuperwriterApplicationService` 仍是一个超大类（1800+ 行），虽已委托子服务但入口过于集中
- MutationPolicyEngine 为 stub 实现，核心审批逻辑已移除，所有变更实际都是 auto_applied
- 两套存储（SQLite + FileStore）之间无同步机制，数据可能不一致
- 前端 EditorView 的文件保存功能标记为 TODO，尚未实现
- Pipeline 对话历史存储在内存 dict 中，进程重启后丢失
- RAG 检索使用简单的关键词匹配（split + 交集计数），无向量检索能力
- SSE 事件流对慢消费者直接丢弃事件，无重试机制
- 前端无 UI 库，使用原生 CSS 类名（`surface-panel`、`product-nav-link` 等自定义设计系统）
