import { QueryClientProvider } from '@tanstack/react-query';
import { createBrowserRouter, RouterProvider } from 'react-router';

import { createAppQueryClient } from '../app/queryClient';
import { appRoutes } from '../app/router';

const queryClient = createAppQueryClient();

const router = createBrowserRouter(appRoutes(queryClient));

export function AppProviders() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
