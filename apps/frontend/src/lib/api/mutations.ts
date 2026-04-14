import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient, type SkillUpsertParams } from './client';

export function useUpsertSkill(context: { projectId: string; novelId: string }) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: SkillUpsertParams) =>
      apiClient.upsertSkill({
        projectId: context.projectId,
        novelId: context.novelId,
        params,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api', 'skills', context.projectId, context.novelId] });
    },
  });
}

export function useImportSkill(context: { projectId: string; novelId: string }) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: { name: string; instruction: string; description?: string; style_scope?: string; is_active?: boolean; donor_kind?: string }) =>
      apiClient.importSkill({ ...context, params }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api', 'skills', context.projectId, context.novelId] });
    },
  });
}

export function useRollbackSkill(context: { projectId: string; novelId: string }) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: { skill_object_id: string; target_revision_id: string }) =>
      apiClient.rollbackSkill({
        projectId: context.projectId,
        novelId: context.novelId,
        params,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api', 'skills', context.projectId, context.novelId] });
    },
  });
}

export function useSaveProvider() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: Record<string, unknown>) => apiClient.saveProvider(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api', 'settings'] });
    },
  });
}

export function useActivateProvider() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (providerId: string) => apiClient.activateProvider(providerId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api', 'settings'] });
    },
  });
}

export function useDeleteProvider() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (providerId: string) => apiClient.deleteProvider(providerId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api', 'settings'] });
    },
  });
}

export function useTestProvider() {
  return useMutation({
    mutationFn: (providerId: string) => apiClient.testProvider(providerId),
  });
}
