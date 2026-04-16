import { useState, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';

import { electronClient } from '../lib/api/electron-client';

export interface Provider {
  provider_id: string;
  provider_name: string;
  base_url: string;
  api_key: string;
  model_name: string;
  temperature: number;
  max_tokens: number;
  is_active: boolean;
}

interface TestResult {
  success: boolean;
  status?: number;
  error?: string;
}

interface Props {
  onEditProvider?: (provider: Provider) => void;
  onAddProvider?: () => void;
}

export function SettingsPanel({ onEditProvider, onAddProvider }: Props) {
  const [testResults, setTestResults] = useState<Record<string, TestResult>>({});

  const { data, refetch, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: async () => {
      const result = await electronClient.getSettings();
      return result.settings;
    },
  });

  const handleTest = useCallback(async (provider: Provider) => {
    const result = await electronClient.testProvider(provider.provider_id) as unknown as TestResult;
    setTestResults(prev => ({ ...prev, [provider.provider_id]: result }));
  }, []);

  const handleActivate = useCallback(async (providerId: string) => {
    await electronClient.activateProvider(providerId);
    await refetch();
  }, [refetch]);

  const handleDelete = useCallback(async (providerId: string) => {
    if (!confirm('确定要删除这个 Provider 吗？')) return;
    await electronClient.deleteProvider(providerId);
    await refetch();
  }, [refetch]);

  const providers = (data?.providers ?? []) as unknown as Provider[];
  const activeProviderId = (data?.active_provider as unknown as Provider | null)?.provider_id;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
      <div className="panel-content" style={{ flex: 1, overflow: 'auto' }}>
        {isLoading && <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>加载中…</p>}

        {providers.length === 0 && !isLoading && (
          <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>暂无 Provider，点击下方添加</p>
        )}

        {providers.map(provider => {
          const testResult = testResults[provider.provider_id];
          const isActive = provider.provider_id === activeProviderId;
          return (
            <div key={provider.provider_id} style={{ marginBottom: 12, padding: '8px', background: 'var(--bg-secondary)', borderRadius: 6 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                <strong style={{ fontSize: 13 }}>{provider.provider_name}</strong>
                {isActive && <span style={{ fontSize: 10, background: 'var(--accent)', color: '#fff', padding: '1px 6px', borderRadius: 10 }}>使用中</span>}
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6 }}>{provider.model_name}</div>
              {testResult && (
                <div style={{ fontSize: 11, color: testResult.success ? '#4ec9b0' : '#f48771', marginBottom: 4 }}>
                  {testResult.success ? `连接成功 (${testResult.status})` : `失败: ${testResult.error || `HTTP ${testResult.status}`}`}
                </div>
              )}
              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                <button type="button" className="btn" style={{ fontSize: 11, padding: '2px 8px' }} onClick={() => handleTest(provider)}>测试</button>
                {!isActive && <button type="button" className="btn btn-primary" style={{ fontSize: 11, padding: '2px 8px' }} onClick={() => handleActivate(provider.provider_id)}>激活</button>}
                <button type="button" className="btn" style={{ fontSize: 11, padding: '2px 8px' }} onClick={() => onEditProvider?.(provider)}>编辑</button>
                <button type="button" className="btn" style={{ fontSize: 11, padding: '2px 8px', color: '#f48771' }} onClick={() => handleDelete(provider.provider_id)}>删除</button>
              </div>
            </div>
          );
        })}
      </div>

      <div style={{ padding: '8px 0 0', borderTop: '1px solid var(--border)' }}>
        <button type="button" className="btn btn-primary" style={{ width: '100%', fontSize: 12 }} onClick={() => onAddProvider?.()}>
          + 添加 Provider
        </button>
      </div>
    </div>
  );
}
