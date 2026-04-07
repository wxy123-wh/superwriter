import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createBrowserRouter } from 'react-router';
import { RouterProvider } from 'react-router/dom';

import { FrontendShell } from '../routes/FrontendShell';

const queryClient = new QueryClient();

function detectBasename(pathname: string): string {
  return pathname === '/app' || pathname.startsWith('/app/') ? '/app' : '/';
}

const router = createBrowserRouter(
  [
    {
      path: '/',
      Component: FrontendShell,
    },
    {
      path: '*',
      Component: FrontendShell,
    },
  ],
  {
    basename: detectBasename(window.location.pathname),
  },
);

export function AppProviders() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
