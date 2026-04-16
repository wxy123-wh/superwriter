import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiClient } from './client';

// Mock global fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

function mockResponse(data: unknown, ok = true) {
  return {
    ok,
    status: ok ? 200 : 400,
    async json() { return data; },
  } as unknown as Response;
}

beforeEach(() => {
  mockFetch.mockReset();
});

describe('apiClient', () => {
  describe('getStartup', () => {
    it('returns startup snapshot', async () => {
      mockFetch.mockResolvedValue(mockResponse({
        ok: true,
        data: {
          startup: {
            workspace_contexts: [
              { project_id: 'p1', project_title: 'Test Project', novel_id: 'n1', novel_title: 'Test Novel' },
            ],
            has_workspace_contexts: true,
          },
        },
      }));

      const result = await apiClient.getStartup();
      expect(result.startup.workspace_contexts).toHaveLength(1);
      expect(result.startup.workspace_contexts[0].project_title).toBe('Test Project');
    });
  });

  describe('getSettings', () => {
    it('returns provider settings', async () => {
      mockFetch.mockResolvedValue(mockResponse({
        ok: true,
        data: {
          settings: {
            providers: [
              { provider_id: 'prov1', provider_name: 'Test Provider', base_url: 'https://api.test.com', api_key: 'sk-test', model_name: 'gpt-4', temperature: 0.7, max_tokens: 4096, is_active: true },
            ],
            active_provider: { provider_id: 'prov1', provider_name: 'Test Provider' },
          },
        },
      }));

      const result = await apiClient.getSettings();
      expect(result.settings.providers).toHaveLength(1);
      expect(result.settings.providers[0].provider_name).toBe('Test Provider');
    });
  });

  describe('getSkills', () => {
    it('returns skill workshop snapshot', async () => {
      mockFetch.mockResolvedValue(mockResponse({
        ok: true,
        data: {
          workshop: {
            project_id: 'p1',
            novel_id: 'n1',
            skills: [
              {
                object_id: 'skobj_001',
                revision_id: 'skrev_001',
                revision_number: 1,
                name: 'Test Skill',
                description: 'A test skill',
                instruction: 'Write well',
                style_scope: 'general',
                is_active: true,
                source_kind: 'manual',
                donor_kind: null,
                payload: {},
              },
            ],
            selected_skill: null,
            versions: [],
            comparison: null,
          },
        },
      }));

      const result = await apiClient.getSkills({ projectId: 'p1', novelId: 'n1' });
      expect(result.workshop.skills).toHaveLength(1);
      expect(result.workshop.skills[0].name).toBe('Test Skill');
    });
  });
});
