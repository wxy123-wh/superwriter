# superwriter — 代码分析报告

> 生成日期: 2026-04-16 | 语言: typescript, javascript | 文件数: 174

## 一、功能模块

| # | 模块 | 核心成员 | 节点数 | 核心文件 |
|---|------|---------|--------|---------|
| 1 | **AppShell.tsx** | `ActivityBar()`, `buildProductRouteHref()`, `getFileLanguage()`, `readRouteSearch()` +14 | 33 | ActivityBar.tsx, AppShell.tsx, ChatPanel.tsx +12 |
| 2 | **client.ts** | `ApiContractError`, `.constructor()`, `ApiResponseError`, `.constructor()` +21 | 28 | SkillVersionList.tsx, client.test.ts, client.ts |
| 3 | **manifest-repository.ts** | `addCharacter()`, `addLocation()`, `addTimelineEvent()`, `createEmptyManifest()` +14 | 19 | manifest-repository.ts |
| 4 | **ManifestView.tsx** | `handleAddCharacter()`, `handleAddLocation()`, `handleAddTimelineEvent()`, `handleEditCharacter()` +5 | 12 | ManifestView.tsx, NovelManifestContext.tsx, novel-manifest.ts |
| 5 | **ConsistencyView.tsx** | `checkConsistency()`, `compareWithPrevious()`, `getIssueTypeLabel()`, `getSeverityBadge()` +3 | 12 | ConsistencyView.tsx, chapter-snapshot.ts, consistency-checker.ts +2 |
| 6 | **main.ts** | `AppProviders()`, `createWindow()`, `getNovelsDir()`, `getProjectDir()` +4 | 11 | AppProviders.tsx, main.ts, queryClient.ts |
| 7 | **ForeshadowRepository** | `ForeshadowRepository`, `.add()`, `.delete()`, `.getByChapter()` +6 | 11 | foreshadow-repository.ts |
| 8 | **mutations.ts** | `createWrapper()`, `useActivateProvider()`, `useDeleteProvider()`, `useImportSkill()` +4 | 10 | mutations.test.tsx, mutations.ts |
| 9 | **SnapshotRepository** | `getSnapshotFilePath()`, `getSnapshotsDir()`, `SnapshotRepository`, `.delete()` +4 | 9 | snapshot-repository.ts |
| 10 | **content-extractor.ts** | `extractCharacters()`, `extractContent()`, `extractLocations()`, `extractObjectMentions()` +1 | 6 | content-extractor.ts |
| 11 | **FileTree.tsx** | `FileTree()`, `handleClick()` | 4 | FileTree.tsx, FileTreeNode.tsx |
| 12 | **db.ts** | `closeDb()`, `getDb()`, `initializeSchema()` | 4 | db.ts |
| 13 | **api-contract.ts** | `apiErr()`, `apiOk()` | 3 | api-contract.ts |

*其他小模块 (12 个): eslint.config.js, playwright.config.ts, setup.ts, vite-env.d.ts, smoke.spec.ts, vite.config.ts, vitest.config.ts, preload.ts*

## 二、需要改进的地方

### 死代码 (JS/TS)

**死文件 (3 个)** — 没有任何地方 import 这些文件：

- `apps/frontend/src/components/SkillVersionList.tsx`
- `apps/frontend/src/lib/api/index.ts`
- `apps/server/src/preload.ts`

**未使用的导出 (18 个)**：

- `apps/frontend/src/app/AppShell.tsx`: `buildProductRouteHref`
- `apps/frontend/src/lib/api/client.ts`: `PIPELINE_META`
- `apps/server/src/repositories/manifest-repository.ts`: `addCharacter`, `updateCharacter`, `deleteCharacter`, `addLocation`, `updateLocation` +7
- `apps/server/src/services/content-extractor.ts`: `extractCharacters`, `extractLocations`, `extractTimeMarkers`, `extractObjectMentions`

**未使用的依赖 (3 个)** — 可从 package.json 移除：

- `@testing-library/user-event`
- `electron`
- `react-router-dom`

**未声明的依赖 (1 个)** — 代码在用但 package.json 没声明：

- `monaco-editor`

### 重复代码

共 **0 处**重复，**0 行**重复代码（占比 0%）

**跨文件重复**（可能需要提取公共模块）：

- `apps\frontend\src\styles\vscode-light-theme.css:96-147` ≡ `apps\frontend\src\styles\vscode-theme.css:130-181` (52 行)
- `apps\frontend\src\types\chapter-snapshot.ts:1-26` ≡ `apps\server\src\repositories\snapshot-repository.ts:9-34` (26 行)
- `apps\frontend\src\lib\api\client.ts:419-434` ≡ `apps\frontend\src\lib\api\electron-client.ts:45-60` (16 行)
- `apps\frontend\src\types\novel-manifest.ts:36-51` ≡ `apps\server\src\repositories\manifest-repository.ts:41-56` (16 行)
- `apps\frontend\src\lib\api\client.ts:529-543` ≡ `apps\frontend\src\lib\api\electron-client.ts:142-156` (15 行)
- `apps\frontend\src\types\novel-manifest.ts:8-22` ≡ `apps\server\src\repositories\manifest-repository.ts:13-27` (15 行)
- `apps\frontend\src\types\foreshadow.ts:1-14` ≡ `apps\server\src\repositories\foreshadow-repository.ts:5-18` (14 行)

**文件内重复** (11 处)：

- `apps\server\src\main.ts`: 5 处内部重复
- `apps\frontend\src\views\ManifestView.tsx`: 3 处内部重复
- `apps\frontend\src\lib\api\mutations.ts`: 1 处内部重复
- `apps\frontend\src\lib\api\mutations.test.tsx`: 1 处内部重复
- `apps\frontend\src\views\ForeshadowView.tsx`: 1 处内部重复

### 高耦合节点

这些节点连接了大量其他模块，修改时影响面大：

| 节点 | 文件 | 连接数 |
|------|------|--------|
| `loadManifest()` | `manifest-repository.ts` | **15** |
| `saveManifest()` | `manifest-repository.ts` | **15** |
| `assertRecord()` | `client.ts` | **12** |
| `ForeshadowRepository` | `foreshadow-repository.ts` | **10** |
| `expectString()` | `client.ts` | **9** |
| `parseSkillWorkshopSkill()` | `client.ts` | **8** |

### 孤立文件

这些文件没有被任何其他文件引用：

- `apps/frontend/dist/assets/index-DXciRHSH.js`

## 三、分析数据摘要

```
节点数: 174
依赖边: 264
功能社区: 13
小社区: 12
dependency_cruiser: ✅
knip: ✅
eslint_complexity: ❌ 'eslint' is not recognized as an internal or external comman
jscpd: ✅
```

---
*工具: npsl-analyze v2.0 | 2026-04-16*