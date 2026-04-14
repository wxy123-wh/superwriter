import { useLocation, useNavigation } from 'react-router';
import { NavLink, Outlet, isRouteErrorResponse, useRouteError } from 'react-router';

import { ApiContractError, ApiResponseError } from '../lib/api/client';

export interface RouteSearchContext {
  projectId: string | null;
  novelId: string | null;
}

export interface ProductRouteDefinition {
  id: string;
  path: string;
  label: string;
  requiresProject: boolean;
  requiresNovel: boolean;
}

export const productRoutes: ProductRouteDefinition[] = [
  {
    id: 'editor',
    path: '/editor',
    label: '编辑器',
    requiresProject: true,
    requiresNovel: true,
  },
  {
    id: 'skills',
    path: '/skills',
    label: '技能工坊',
    requiresProject: true,
    requiresNovel: true,
  },
  {
    id: 'settings',
    path: '/settings',
    label: '设置',
    requiresProject: false,
    requiresNovel: false,
  },
];

export function readRouteSearch(search: string): RouteSearchContext {
  const params = new URLSearchParams(search);
  return {
    projectId: params.get('project_id'),
    novelId: params.get('novel_id'),
  };
}

export function buildProductRouteHref(path: string, context: RouteSearchContext): string {
  const params = new URLSearchParams();
  if (context.projectId) params.set('project_id', context.projectId);
  if (context.novelId) params.set('novel_id', context.novelId);
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}

export function AppShell() {
  const location = useLocation();
  const navigation = useNavigation();
  const context = readRouteSearch(location.search);
  const currentRoute = productRoutes.find(
    (route) => location.pathname === route.path || location.pathname.startsWith(`${route.path}/`),
  );

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="app-sidebar-top">
          <div className="app-brand">
            <div className="app-brand-mark" aria-hidden="true">SW</div>
            <div>
              <p className="eyebrow">SuperWriter</p>
              <h1>节点写作助手</h1>
            </div>
          </div>
        </div>
        <nav aria-label="产品导航" className="product-nav">
          {productRoutes.map((route) => {
            const isDisabled =
              (route.requiresProject && !context.projectId) || (route.requiresNovel && !context.novelId);
            return isDisabled ? (
              <div key={route.id} aria-disabled="true" className="product-nav-link product-nav-link-disabled">
                <strong>{route.label}</strong>
              </div>
            ) : (
              <NavLink
                key={route.id}
                to={buildProductRouteHref(route.path, context)}
                className={({ isActive }) =>
                  isActive ? 'product-nav-link product-nav-link-active' : 'product-nav-link'
                }
              >
                <strong>{route.label}</strong>
              </NavLink>
            );
          })}
        </nav>
      </aside>
      <div className="app-content">
        <header className="app-header">
          <div className="app-header-copy">
            <h2>{currentRoute?.label ?? 'SuperWriter'}</h2>
          </div>
          {navigation.state !== 'idle' ? <p className="status-pill">加载中…</p> : null}
        </header>
        <main className="surface-view">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export function RouteErrorBoundary() {
  const error = useRouteError();
  if (isRouteErrorResponse(error)) {
    return (
      <section className="surface-panel surface-panel-error">
        <p className="eyebrow">Route error</p>
        <h2>路由加载失败</h2>
        <p>{error.status} {error.statusText}</p>
        <p>{typeof error.data === 'string' ? error.data : '无法完成当前路由。'}</p>
      </section>
    );
  }
  if (error instanceof ApiResponseError) {
    return (
      <section className="surface-panel surface-panel-error">
        <p className="eyebrow">API error</p>
        <h2>接口返回了明确错误</h2>
        <p>{error.status} · {error.code}</p>
        <p>{error.message}</p>
      </section>
    );
  }
  if (error instanceof ApiContractError) {
    return (
      <section className="surface-panel surface-panel-error">
        <p className="eyebrow">Contract drift</p>
        <h2>接口契约与前端预期不一致</h2>
        <p>{error.endpoint}</p>
        <p>{error.message}</p>
      </section>
    );
  }
  return (
    <section className="surface-panel surface-panel-error">
      <p className="eyebrow">Unexpected error</p>
      <h2>出现未处理错误</h2>
      <p>{error instanceof Error ? error.message : '未知错误'}</p>
    </section>
  );
}
