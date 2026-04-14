# SuperWriter - 前端规范

## 技术栈

- React 19 + TypeScript 5.9（使用最新 React 特性，但依赖生态兼容性待验证）
- Vite 7 构建（开发 HMR 快，但大型项目可能遇到预构建缓慢问题）
- React Router 7（文件系统路由风格，loader 预取数据）
- TanStack React Query 5（自动缓存 + 后台刷新，前端不手动管理请求状态）
- Monaco Editor（与 VS Code 同内核的编辑器组件，功能强大但打包体积大）
- 无 UI 组件库，使用自定义 CSS 设计系统（`surface-panel`、`product-nav-link` 等语义化类名，一致性依赖开发者自律）
- 无状态管理库（React Query 管理服务端状态，本地状态用 useState）

## 页面/路由

| 路径 | 组件 | 用途 |
|------|------|------|
| `/` | `StartupView` | 启动页，显示已有工作区列表或创建新项目入口 |
| `/editor` | `EditorView` | Monaco 代码编辑器 + 文件树，编辑工作区内的文件 |
| `/skills` | `SkillsView` | 技能工坊，管理作者控制技能（CRUD + 版本历史 + diff） |
| `/settings` | `SettingsView` | AI 提供者配置管理（添加/激活/测试/删除提供者） |

所有路由嵌套在 `AppShell` 布局组件下，提供侧边栏导航 + 顶部标题栏。

## 数据获取

- 使用 React Router 的 `loader` 函数在路由切换前预取数据（通过 `queryClient.ensureQueryData` 桥接到 React Query）
- API 调用集中在 `apiClient` 对象中，每个方法对应一个后端 API 端点
- 所有 API 响应经过手写 parser 函数严格校验字段类型（非 `as any` 断言，而是 `assertRecord` + `expectString` 等运行时检查）
- 支持 Electron IPC 双通道：`isElectron()` 检测环境，Electron 下走 IPC 而非 HTTP（为桌面客户端预留）
- 错误分类为 `ApiResponseError`（后端返回的业务错误）和 `ApiContractError`（前后端契约不匹配），在 `RouteErrorBoundary` 中分别展示

### 缓存策略
- 通过 React Query 的 `queryKey` 自动管理缓存
- Skills 查询 key 包含 `projectId + novelId`（切换小说自动重新拉取）
- Settings 和 Startup 查询 key 不含项目参数（全局共享）
- 写操作（mutation）后手动使相关 query 失效以触发刷新

## 组件架构

### AppShell（布局组件）
- 左侧边栏：品牌标识 + 产品导航链接列表
- 导航项根据上下文（projectId/novelId）动态拼接 URL query 参数
- 需要项目/小说上下文但未提供时，导航项显示为禁用状态（`aria-disabled="true"`）
- 顶部标题栏：当前路由标签 + 加载状态指示器
- `RouteErrorBoundary` 区分 4 种错误类型渲染不同提示

### EditorView（编辑器视图）
- 左侧文件树（`FileTree` + `FileTreeNode`）+ 右侧 Monaco Editor 的经典 IDE 布局
- 目录按需加载（点击展开时才请求子目录内容）
- 文件内容加载后渲染 Monaco Editor（markdown 语法高亮模式）
- 文件保存功能尚未实现（`handleContentChange` 中标记 TODO）

### SkillsView（技能工坊视图）
- 技能列表 + 创建/编辑表单
- 版本历史列表（`SkillVersionList`）
- 版本间 diff 对比查看
- 支持创建、更新、切换激活状态、回滚、导入 5 种操作

### StartupView（启动视图）
- 已有工作区列表（project + novel 组合）
- 创建新小说的表单（小说标题 + 项目标题 + 文件夹路径）
- 创建成功后跳转到编辑器视图

### SettingsView（设置视图）
- AI 提供者配置列表
- 添加/编辑提供者表单（provider_name, base_url, api_key, model_name, temperature, max_tokens）
- 激活/删除/测试提供者按钮

## 路由上下文传递

项目 ID 和小说 ID 通过 URL query 参数（`?project_id=xxx&novel_id=yyy`）在路由间传递，而非 React Context 或全局状态。`readRouteSearch()` 统一解析，`buildProductRouteHref()` 统一拼接。所有需要上下文的 API 调用从 URL 参数中读取。

## API 客户端契约

前端 `apiClient` 对每个 API 响应执行完整的运行时类型校验：
- 每个字段用 `expectString`/`expectNumber`/`expectBoolean` 逐一检查
- 嵌套对象用 `assertRecord`，数组用 `expectArray` + 逐元素 parser
- 响应信封格式：`{ ok: true, data: {...} }` 或 `{ ok: false, error: { code, message, details } }`
- 这意味着后端新增字段不会破坏前端，但后端删除/重命名字段会立即触发 `ApiContractError`

## 已知限制

- Monaco Editor 打包体积较大（~2MB gzipped），首次加载较慢
- 文件树仅支持按需加载目录，不支持文件搜索/过滤
- 无国际化框架，中文硬编码在组件中
- 无暗色模式切换
- 未实现工作台（workbench）流水线的前端 UI（路由定义了 `PipelineView` 但未在 router 中挂载）
- 测试基础设施已配置（Vitest + Testing Library + Playwright）但实际测试覆盖情况未知
