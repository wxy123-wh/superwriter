import type { QueryClient } from '@tanstack/react-query';
import type { RouteObject } from 'react-router';

import { AppShell, RouteErrorBoundary } from './AppShell';
import { EditorView } from '../views/EditorView';
import { SkillsView } from '../views/SkillsView';
import { ForeshadowView } from '../views/ForeshadowView';
import { ManifestView } from '../views/ManifestView';
import { ConsistencyView } from '../views/ConsistencyView';
import { SettingsView } from '../views/SettingsView';


export function appRoutes(_queryClient: QueryClient): RouteObject[] {
  return [
    {
      path: '/',
      Component: AppShell,
      errorElement: <RouteErrorBoundary />,
      children: [
        {
          index: true,
          Component: EditorView,
        },
        {
          path: 'skills',
          Component: SkillsView,
        },
        {
          path: 'foreshadows',
          Component: ForeshadowView,
        },
        {
          path: 'manifest',
          Component: ManifestView,
        },
        {
          path: 'consistency',
          Component: ConsistencyView,
        },
        {
          path: 'settings',
          Component: SettingsView,
        },
      ],
    },
  ];
}
