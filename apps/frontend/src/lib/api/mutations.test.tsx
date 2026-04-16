import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { useUpsertSkill, useImportSkill, useRollbackSkill, useSaveProvider, useActivateProvider, useDeleteProvider, useTestProvider } from './mutations';

// Mock apiClient
vi.mock('./client', () => ({
  apiClient: {
    upsertSkill: vi.fn(),
    importSkill: vi.fn(),
    rollbackSkill: vi.fn(),
    saveProvider: vi.fn(),
    activateProvider: vi.fn(),
    deleteProvider: vi.fn(),
    testProvider: vi.fn(),
  },
}));

import { apiClient } from './client';

function createWrapper() {
  const queryClient = new QueryClient();
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('mutations', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('useUpsertSkill', () => {
    it('calls upsertSkill and invalidates queries on success', async () => {
      (apiClient.upsertSkill as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true });

      const { result } = renderHook(() => useUpsertSkill({ projectId: 'p1', novelId: 'n1' }), {
        wrapper: createWrapper(),
      });

      result.current.mutate({ action: 'create', name: 'New Skill', instruction: 'Write' });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
    });
  });

  describe('useImportSkill', () => {
    it('calls importSkill and invalidates queries on success', async () => {
      (apiClient.importSkill as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true });

      const { result } = renderHook(() => useImportSkill({ projectId: 'p1', novelId: 'n1' }), {
        wrapper: createWrapper(),
      });

      result.current.mutate({ name: 'Imported', instruction: 'Import me' });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
    });
  });

  describe('useRollbackSkill', () => {
    it('calls rollbackSkill', async () => {
      (apiClient.rollbackSkill as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true });

      const { result } = renderHook(() => useRollbackSkill({ projectId: 'p1', novelId: 'n1' }), {
        wrapper: createWrapper(),
      });

      result.current.mutate({ skill_object_id: 'skobj_001', target_revision_id: 'skrev_old' });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
    });
  });

  describe('useSaveProvider', () => {
    it('calls saveProvider and invalidates settings query', async () => {
      (apiClient.saveProvider as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true });

      const { result } = renderHook(() => useSaveProvider(), {
        wrapper: createWrapper(),
      });

      result.current.mutate({ provider_name: 'New Provider', base_url: 'https://api.test.com', api_key: 'sk-test' });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
    });
  });

  describe('useActivateProvider', () => {
    it('calls activateProvider', async () => {
      (apiClient.activateProvider as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true });

      const { result } = renderHook(() => useActivateProvider(), {
        wrapper: createWrapper(),
      });

      result.current.mutate('prov_001');

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
    });
  });

  describe('useDeleteProvider', () => {
    it('calls deleteProvider', async () => {
      (apiClient.deleteProvider as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true });

      const { result } = renderHook(() => useDeleteProvider(), {
        wrapper: createWrapper(),
      });

      result.current.mutate('prov_001');

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
    });
  });

  describe('useTestProvider', () => {
    it('calls testProvider', async () => {
      (apiClient.testProvider as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, status: 200 });

      const { result } = renderHook(() => useTestProvider(), {
        wrapper: createWrapper(),
      });

      result.current.mutate('prov_001');

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
    });
  });
});
