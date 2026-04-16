import type { Foreshadow } from '../../types/foreshadow';

const api = typeof window !== 'undefined' ? window.electronAPI : undefined;
const hasElectronAPI = api && typeof api.invoke === 'function';

export const foreshadowApi = {
  load: (projectId: string) => {
    if (!hasElectronAPI || !api) return Promise.resolve({ foreshadows: [] as Foreshadow[] });
    return api.invoke('loadForeshadows', { projectId }) as Promise<{ foreshadows: Foreshadow[]; error?: string }>;
  },

  save: (projectId: string, foreshadows: Foreshadow[]) => {
    if (!hasElectronAPI || !api) return Promise.resolve({ success: false, error: 'Electron API not available' });
    return api.invoke('saveForeshadows', { projectId, foreshadows }) as Promise<{ success: boolean; error?: string }>;
  },
};
