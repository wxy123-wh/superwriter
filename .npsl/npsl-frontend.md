# SuperWriter - 前端规范

## 技术栈

- React 19 + TypeScript 5.9（函数组件 + hooks，无 class 组件）
- Vite 7 构建（开发时 HMR，生产时打包为静态文件由 Electron loadFile 加载）
- React Router 7（嵌套路由，所有视图在 AppShell 布局组件内通过 `<Outlet />` 切换）
- TanStack React Query 5（服务端状态管理 + mutation hooks 封装缓存失效）
- Monaco Editor `@monaco-editor/react`（同步 import，首屏增加 3-5 秒，未做懒加载）
- 无 CSS 框架/UI 组件库（纯手写样式）
- 无全局状态管理库（通过 React Context + Query Client 管理跨组件状态）

## 页面/路由

| 路径 | 组件 | 用途 |
|------|------|------|
| `/` | `EditorView` | 默认视图：Monaco 代码编辑器，编辑选中的文件 |
| `/skills` | `SkillsView` | AI 写作技能管理：创建/编辑/导入/回滚技能 |
| `/foreshadows` | `ForeshadowView` | 伏笔管理：追踪已埋设和已解决的伏笔 |
| `/manifest` | `ManifestView` | 世界观管理：角色/地点/时间线/追踪物品的 CRUD |
| `/consistency` | `ConsistencyView` | 一致性校验：提取章节内容 → 对比快照 → 发现冲突 |

所有路由嵌套在 `AppShell` 布局组件内，共享 TitleBar + ActivityBar + FileTree 侧边栏 + StatusBar。路由错误由 `RouteErrorBoundary` 捕获。

## 数据获取

### IPC 通信层

前端通过 `electron-client.ts` 封装的 `electronClient` 对象与主进程通信：
- 所有方法调用 `window.electronAPI!.invoke(channel, params)`（preload 暴露的 bridge）
- `isElectron()` 检测运行环境（`window.electronAPI !== undefined`）
- `electronClient` 提供 18 个方法，覆盖所有 IPC 端点的类型安全封装

### HTTP 备用客户端

- `client.ts`（611 行，25 个导出）定义了一套基于 HTTP fetch 的备用客户端
- 包含完整的运行时类型校验体系（`assertRecord`、`expectString`、`parseEnvelope` 等）
- 两种自定义错误：`ApiContractError`（响应结构不符预期）和 `ApiResponseError`（服务端返回错误）
- Electron 环境下不使用 HTTP 客户端，但类型定义被 electron-client 复用

### 缓存策略

- TanStack React Query 管理请求缓存和 mutation 乐观更新
- `createAppQueryClient()` 创建全局 QueryClient 实例
- 9 个 mutation hooks 封装了缓存失效逻辑（`useUpsertSkill`、`useImportSkill`、`useRollbackSkill`、`useSaveProvider`、`useActivateProvider`、`useDeleteProvider`、`useTestProvider`）
- 无显式缓存过期时间配置（使用 React Query 默认值）

## 组件架构

### 布局层

| 组件 | 职责 | 特别说明 |
|------|------|----------|
| `AppShell` | 全局布局 + 文件管理状态 | 状态最重的组件（12+ 个 useState），管理 localRootPath/fileTree/selectedPath/fileContent/isDirty/fileLanguage/activeView 等 |
| `TitleBar` | 窗口标题栏 | 显示应用标题 |
| `ActivityBar` | 左侧活动栏 | 切换 explorer / search / chat 三个侧边面板 |
| `FileTree` | 文件树容器 | 递归渲染 FileTreeNode，支持目录展开/折叠 |
| `FileTreeNode` | 文件树节点 | 点击文件触发加载，点击目录触发展开 |
| `StatusBar` | 底部状态栏 | 显示当前文件路径等信息 |
| `EditorTabs` | 编辑器标签页 | 多文件标签（当前实现为单文件编辑模式） |

### 功能视图

| 组件 | 职责 | 特别说明 |
|------|------|----------|
| `EditorView` | Monaco 编辑器包装 | 接收 AppShell 传递的 EditorContext 渲染编辑器 |
| `MonacoEditor` | Monaco Editor 封装 | 同步 import `@monaco-editor/react`（未做 `React.lazy` 懒加载） |
| `ChatPanel` | AI 聊天面板 | 消息列表 + 输入框，`scrollToBottom` 自动滚动到最新消息 |
| `SkillsView` | 技能管理视图 | 技能列表 + 编辑器 + 创建/保存/导入操作，`parseSkillContent` 解析技能内容格式 |
| `SkillVersionList` | 技能版本列表 | **死文件**（未被任何组件引用），本应展示版本历史 |
| `ForeshadowView` | 伏笔管理视图 | 通过 `useForeshadows` hook 获取/操作伏笔数据 |
| `ManifestView` | 世界观管理视图 | 575 行，职责过多：角色 CRUD + 地点 CRUD + 时间线 CRUD + 物品追踪，全部在一个组件内 |
| `ConsistencyView` | 一致性校验视图 | 提取章节内容 → 保存快照 → `checkConsistency` + `compareWithPrevious` 校验 |

### Context 层

| Context | 职责 |
|---------|------|
| `NovelManifestProvider` / `useNovelManifest` | 全局小说世界观数据访问（manifest CRUD 操作封装为 context 方法，234 行） |
| `AppProviders` | 顶层 Provider 组装（QueryClientProvider + Router + NovelManifestProvider） |

### Hooks 层

| Hook | 文件 | 职责 |
|------|------|------|
| `useChapterSnapshot` | `hooks/useChapterSnapshot.ts` | 封装章节快照的 IPC 加载/保存逻辑 |
| `useForeshadows` | `hooks/useForeshadows.ts` | 封装伏笔列表的 IPC 加载/保存逻辑 |
| `useUpsertSkill` | `lib/api/mutations.ts` | mutation：创建/更新技能 |
| `useImportSkill` | `lib/api/mutations.ts` | mutation：导入技能 |
| `useRollbackSkill` | `lib/api/mutations.ts` | mutation：回滚技能版本 |
| `useSaveProvider` | `lib/api/mutations.ts` | mutation：保存 AI 提供商 |
| `useActivateProvider` | `lib/api/mutations.ts` | mutation：激活 AI 提供商 |
| `useDeleteProvider` | `lib/api/mutations.ts` | mutation：删除 AI 提供商 |
| `useTestProvider` | `lib/api/mutations.ts` | mutation：测试 AI 提供商连通性 |

### 业务逻辑层

| 模块 | 职责 |
|------|------|
| `consistency-checker.ts` | 章节一致性校验：对比 snapshot 与 manifest（检测角色未知状态、谜团数异常），对比前后 snapshot（检测死人复活、秘密遗失） |

## 前端类型重复问题

前端和后端之间存在类型重复定义：
- `packages/shared/src/types/skill.types.ts` 定义了技能相关类型（132 行）
- `apps/frontend/src/lib/api/client.ts` 重新定义了几乎相同的类型（`SkillWorkshopSkillSnapshot` 等）
- `apps/frontend/src/types/novel-manifest.ts` 定义了前端 manifest 类型
- `apps/server/src/repositories/manifest-repository.ts` 独立定义了一套 manifest 类型
- `apps/frontend/src/types/chapter-snapshot.ts` 定义了快照和一致性问题类型
- `apps/server/src/repositories/snapshot-repository.ts` 独立定义了快照类型
- 共享包 `packages/shared` 存在但未被充分利用，多处类型手动同步

## 已知质量问题

### 死文件
- `apps/frontend/src/components/SkillVersionList.tsx`（未被引用）
- `apps/frontend/src/lib/api/index.ts`（`createUnifiedClient` 未被使用）

### 未使用的导出
- `client.ts` 中的 `PIPELINE_META`（Pipeline 阶段元数据定义了但未使用）
- `AppShell.tsx` 中的 `buildProductRouteHref()`（路由构建辅助函数未被使用）

### 未列入依赖
- `monaco-editor`（被 `@monaco-editor/react` 间接引入，但未在 package.json 声明）

### 性能问题
- Monaco Editor 同步加载（可改为 `React.lazy()` + `Suspense` 按需加载，减少首屏 3-5 秒）
- 多个组件使用 `.map()` 渲染列表但无虚拟滚动（FileTree、ChatPanel、ManifestView、ForeshadowView、ConsistencyView、SkillVersionList 等，数据量大时会卡顿）
- `AppShell` 组件状态过多（12+ 个 useState），任一状态变更触发整个布局重渲染
- `client.ts` 职责过多（611 行，25 个导出，33 条依赖边），建议按领域拆分
