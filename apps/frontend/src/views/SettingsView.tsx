import { useState, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useOutletContext } from 'react-router';

import { electronClient } from '../lib/api/electron-client';

interface ContextType {
  localRootPath: string | null;
}

const defaultContext: ContextType = { localRootPath: null };

interface Provider {
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

export function SettingsView() {
  const ctx = useOutletContext<ContextType>() ?? defaultContext;
  const { localRootPath } = ctx;

  const [showForm, setShowForm] = useState(false);
  const [editingProvider, setEditingProvider] = useState<Provider | null>(null);
  const [formData, setFormData] = useState({
    provider_name: '',
    base_url: '',
    api_key: '',
    model_name: '',
    temperature: '0.7',
    max_tokens: '4096',
  });
  const [testResults, setTestResults] = useState<Record<string, TestResult>>({});
  const [saving, setSaving] = useState(false);

    const { data, refetch, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: async () => {
      const result = await electronClient.getSettings();
      return result.settings;
    },
  });

  const resetForm = useCallback(() => {
    setFormData({
      provider_name: '',
      base_url: '',
      api_key: '',
      model_name: '',
      temperature: '0.7',
      max_tokens: '4096',
    });
    setEditingProvider(null);
    setShowForm(false);
  }, []);

  const handleEdit = useCallback((provider: Provider) => {
    setEditingProvider(provider);
    setFormData({
      provider_name: provider.provider_name,
      base_url: provider.base_url,
      api_key: provider.api_key,
      model_name: provider.model_name,
      temperature: String(provider.temperature),
      max_tokens: String(provider.max_tokens),
    });
    setShowForm(true);
  }, []);

  const handleSave = async () => {
    if (!formData.provider_name || !formData.base_url || !formData.api_key || !formData.model_name) {
      return;
    }
    setSaving(true);
    try {
      await electronClient.saveProvider({
        provider_id: editingProvider?.provider_id,
        provider_name: formData.provider_name,
        base_url: formData.base_url,
        api_key: formData.api_key,
        model_name: formData.model_name,
        temperature: parseFloat(formData.temperature) || 0.7,
        max_tokens: parseInt(formData.max_tokens) || 4096,
      });
      await refetch();
      resetForm();
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async (provider: Provider) => {
    const result = await electronClient.testProvider(provider.provider_id) as unknown as TestResult;
    setTestResults(prev => ({ ...prev, [provider.provider_id]: result }));
  };

  const handleActivate = async (providerId: string) => {
    await electronClient.activateProvider(providerId);
    await refetch();
  };

  const handleDelete = async (providerId: string) => {
    if (!confirm('确定要删除这个 Provider 吗？')) return;
    await electronClient.deleteProvider(providerId);
    await refetch();
  };

  if (!localRootPath) {
    return (
      <div className="command-center">
        <section className="surface-panel">
          <p className="panel-empty">请先打开一个项目文件夹</p>
        </section>
      </div>
    );
  }

  const providers = (data?.providers ?? []) as unknown as Provider[];
  const activeProviderId = (data?.active_provider as unknown as Provider | null)?.provider_id;

  return (
    <div className="command-center">
      <section className="surface-panel">
        <div className="panel-header">
          <h2>AI Provider 设置</h2>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => { resetForm(); setShowForm(true); }}
          >
            添加 Provider
          </button>
        </div>
      </section>

      {isLoading && <section className="surface-panel"><p>加载中…</p></section>}

      {providers.length === 0 && !isLoading && (
        <section className="surface-panel">
          <p className="panel-empty">暂无已配置的 Provider，请点击"添加 Provider"开始配置</p>
        </section>
      )}

      {providers.map(provider => {
        const testResult = testResults[provider.provider_id];
        const isActive = provider.provider_id === activeProviderId;

        return (
          <section key={provider.provider_id} className="surface-panel">
            <div className="provider-header">
              <div className="provider-info">
                <strong>{provider.provider_name}</strong>
                {isActive && <span className="badge badge-active">使用中</span>}
              </div>
              <div className="provider-meta">
                <span className="provider-model">{provider.model_name}</span>
                <span className="provider-url">{provider.base_url}</span>
              </div>
            </div>

            {testResult && (
              <div className={`test-result ${testResult.success ? 'test-success' : 'test-error'}`}>
                {testResult.success
                  ? `连接成功 (${testResult.status})`
                  : `连接失败: ${testResult.error || `HTTP ${testResult.status}`}`}
              </div>
            )}

            <div className="proposal-actions">
              <button type="button" className="btn" onClick={() => handleTest(provider)}>
                测试连接
              </button>
              {!isActive && (
                <button type="button" className="btn btn-primary" onClick={() => handleActivate(provider.provider_id)}>
                  激活
                </button>
              )}
              <button type="button" className="btn" onClick={() => handleEdit(provider)}>
                编辑
              </button>
              <button type="button" className="btn btn-danger" onClick={() => handleDelete(provider.provider_id)}>
                删除
              </button>
            </div>
          </section>
        );
      })}

      {showForm && (
        <section className="surface-panel">
          <h3>{editingProvider ? '编辑 Provider' : '新建 Provider'}</h3>
          <form
            className="inline-form"
            onSubmit={e => { e.preventDefault(); handleSave(); }}
          >
            <div className="form-row">
              <label htmlFor="provider_name">名称</label>
              <input
                id="provider_name"
                type="text"
                className="form-input"
                value={formData.provider_name}
                onChange={e => setFormData(p => ({ ...p, provider_name: e.target.value }))}
                placeholder="例如: OpenAI"
                required
              />
            </div>
            <div className="form-row">
              <label htmlFor="base_url">API Base URL</label>
              <input
                id="base_url"
                type="url"
                className="form-input"
                value={formData.base_url}
                onChange={e => setFormData(p => ({ ...p, base_url: e.target.value }))}
                placeholder="https://api.openai.com/v1"
                required
              />
            </div>
            <div className="form-row">
              <label htmlFor="api_key">API Key</label>
              <input
                id="api_key"
                type="password"
                className="form-input"
                value={formData.api_key}
                onChange={e => setFormData(p => ({ ...p, api_key: e.target.value }))}
                placeholder="sk-..."
                required
              />
            </div>
            <div className="form-row">
              <label htmlFor="model_name">模型</label>
              <input
                id="model_name"
                type="text"
                className="form-input"
                value={formData.model_name}
                onChange={e => setFormData(p => ({ ...p, model_name: e.target.value }))}
                placeholder="gpt-4o"
                required
              />
            </div>
            <div className="form-row-group">
              <div className="form-row">
                <label htmlFor="temperature">Temperature</label>
                <input
                  id="temperature"
                  type="number"
                  className="form-input"
                  value={formData.temperature}
                  onChange={e => setFormData(p => ({ ...p, temperature: e.target.value }))}
                  min="0"
                  max="2"
                  step="0.1"
                />
              </div>
              <div className="form-row">
                <label htmlFor="max_tokens">Max Tokens</label>
                <input
                  id="max_tokens"
                  type="number"
                  className="form-input"
                  value={formData.max_tokens}
                  onChange={e => setFormData(p => ({ ...p, max_tokens: e.target.value }))}
                  min="1"
                />
              </div>
            </div>
            <div className="proposal-actions">
              <button type="submit" className="btn btn-primary" disabled={saving}>
                {saving ? '保存中…' : '保存'}
              </button>
              <button type="button" className="btn" onClick={resetForm}>
                取消
              </button>
            </div>
          </form>
        </section>
      )}
    </div>
  );
}
