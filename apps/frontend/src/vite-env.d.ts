/// <reference types="vite/client" />

declare global {
  interface Window {
    electronAPI?: {
      invoke: (channel: string, data: any) => Promise<any>;
      ping: () => Promise<string>;
    };
  }
}

export {};
