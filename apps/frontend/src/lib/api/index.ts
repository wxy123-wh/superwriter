/**
 * Unified API Client
 * Automatically routes to Electron IPC or HTTP based on environment
 */

import { apiClient as httpClient } from './client';
import { electronClient, isElectron } from './electron-client';

type ApiClient = typeof httpClient;

/**
 * Create a proxy that automatically routes to Electron or HTTP
 */
function createUnifiedClient(): ApiClient {
  return new Proxy(httpClient, {
    get(target, prop: string) {
      // If running in Electron and the method exists in electronClient, use it
      if (isElectron() && prop in electronClient) {
        return (electronClient as any)[prop];
      }
      // Otherwise use HTTP client
      return (target as any)[prop];
    },
  }) as ApiClient;
}

export const unifiedApiClient = createUnifiedClient();

// Re-export types from client
export * from './client';
