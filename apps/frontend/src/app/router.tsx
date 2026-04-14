import { queryOptions } from '@tanstack/react-query';
import type { QueryClient } from '@tanstack/react-query';
import type { RouteObject } from 'react-router';
import { type LoaderFunctionArgs } from 'react-router';

import { AppShell, RouteErrorBoundary, readRouteSearch, type RouteSearchContext } from './AppShell';
import { apiClient } from '../lib/api/client';
import { SkillsView } from '../views/SkillsView';
import { EditorView } from '../views/EditorView';
import { PipelineView } from '../views/PipelineView';

function requireProjectId(context: RouteSearchContext, routeLabel: string): string {
  if (!context.projectId) {
    throw new Response(`${routeLabel} 需要 project_id。`, { status: 400, statusText: 'Missing project_id' });
  }
  return context.projectId;
}

function requireNovelId(context: RouteSearchContext, routeLabel: string): string {
  if (!context.novelId) {
    throw new Response(`${routeLabel} 需要 novel_id。`, { status: 400, statusText: 'Missing novel_id' });
  }
  return context.novelId;
}

function contextFromUrl(requestUrl: string): RouteSearchContext {
  return readRouteSearch(new URL(requestUrl).search);
}

export const skillsOptions = (context: RouteSearchContext) =>
  queryOptions({
    queryKey: ['api', 'skills', context.projectId, context.novelId],
    queryFn: () =>
      apiClient.getSkills({
        projectId: requireProjectId(context, '技能工坊'),
        novelId: requireNovelId(context, '技能工坊'),
      }),
  });

function scopedLoader(queryClient: QueryClient, factory: (context: RouteSearchContext) => unknown) {
  return async ({ request }: LoaderFunctionArgs) => {
    await queryClient.ensureQueryData(factory(contextFromUrl(request.url)) as never);
    return null;
  };
}

export function appRoutes(queryClient: QueryClient): RouteObject[] {
  return [
    {
      path: '/',
      Component: AppShell,
      errorElement: <RouteErrorBoundary />,
      children: [
        {
          path: 'editor',
          Component: EditorView,
        },
        {
          path: 'skills',
          loader: scopedLoader(queryClient, skillsOptions),
          Component: SkillsView,
        },
        {
          path: 'chat',
          Component: PipelineView,
        },
      ],
    },
  ];
}
