import { useState } from 'react';
import { useSuspenseQuery } from '@tanstack/react-query';

import { settingsOptions } from '../app/router';
import { useSaveProvider, useActivateProvider, useDeleteProvider, useTestProvider } from '../lib/api/mutations';

export function SettingsView() {
  const { data } = useSuspenseQuery(settingsOptions());
  const settings = data.settings;

  const saveMutation = useSaveProvider();
  const activateMutation = useActivateProvider();
  const deleteMutation = useDeleteProvider();
  const testMutation = useTestProvider();

  const [showForm, setShowForm] = useState(false);
  const [formProviderName, setFormProviderName] = useState('');
  const [formBaseUrl, setFormBaseUrl] = useState('');
  const [formApiKey, setFormApiKey] = useState('');
  const [formModelName, setFormModelName] = useState('');
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [statusTone, setStatusTone] = useState<'success' | 'error' | null>(null);

  const providers = settings.providers as Array<Record<string, unknown>>;

  const clearStatus = () => {
    setStatusMessage(null);
    setStatusTone(null);
  };

  const handleDeleteProvider = (provider: Record<string, unknown>) => {
    const providerId = String(provider.provider_id ?? '');
    const providerName = String(provider.provider_name ?? '该提供商');

    if (!providerId) {
      setStatusTone('error');
      setStatusMessage('当前提供商缺少 provider_id，暂时无法删除。');
      return;
    }

    if (!window.confirm(`确认删除「${providerName}」？`)) {
      return;
    }

    clearStatus();
    deleteMutation.mutate(providerId, {
      onSuccess: () => {
        setStatusTone('success');
        setStatusMessage(`已删除提供商：${providerName}`);
      },
      onError: (error) => {
        setStatusTone('error');
        setStatusMessage(error instanceof Error ? error.message : '删除失败，请稍后重试。');
      },
    });
  };

  return (
    <div className="command-center">
      <section className="surface-panel">
        <button type="button" className="btn" onClick={() => setShowForm(!showForm)}>
          {showForm ? '取消' : '添加提供商'}
        </button>
        {statusMessage && (
          <p className={`status-message ${statusTone === 'error' ? 'status-message-error' : 'status-message-success'}`} role="status">
            {statusMessage}
          </p>
        )}
        {deleteMutation.isPending && (
          <p className="status-message" role="status">正在删除提供商…</p>
        )}
        {showForm && (
          <form className="inline-form" onSubmit={(e) => {
            e.preventDefault();
            clearStatus();
            saveMutation.mutate(
              {
                provider_name: formProviderName,
                base_url: formBaseUrl,
                api_key: formApiKey,
                model_name: formModelName,
                is_active: settings.active_provider === null,
              },
              {
                onSuccess: () => {
                  setShowForm(false);
                  setFormProviderName('');
                  setFormBaseUrl('');
                  setFormApiKey('');
                  setFormModelName('');
                  setStatusTone('success');
                  setStatusMessage('提供商已保存。');
                },
                onError: (error) => {
                  setStatusTone('error');
                  setStatusMessage(error instanceof Error ? error.message : '保存失败，请稍后重试。');
                },
              },
            );
          }}>
            <input type="text" className="form-input" value={formProviderName} onChange={(e) => setFormProviderName(e.target.value)} placeholder="名称" required />
            <input type="text" className="form-input" value={formBaseUrl} onChange={(e) => setFormBaseUrl(e.target.value)} placeholder="Base URL" required />
            <input type="password" className="form-input" value={formApiKey} onChange={(e) => setFormApiKey(e.target.value)} placeholder="API Key" required />
            <input type="text" className="form-input" value={formModelName} onChange={(e) => setFormModelName(e.target.value)} placeholder="Model" required />
            <button type="submit" className="btn btn-primary" disabled={saveMutation.isPending}>
              {saveMutation.isPending ? '保存中…' : '保存'}
            </button>
          </form>
        )}
        <ul className="object-list">
          {providers.map((provider) => (
            <li key={String(provider.provider_id ?? '')} className="object-item provider-card-row">
              <div className="provider-info">
                <strong>{String(provider.provider_name ?? '')}</strong>
                <span className="version-scope">{String(provider.model_name ?? '')}</span>
                {provider.is_active === true && <span className="version-badge">激活</span>}
              </div>
              <div className="provider-actions-inline">
                {!provider.is_active && (
                  <button type="button" className="btn btn-sm" disabled={activateMutation.isPending}
                    onClick={() => {
                      clearStatus();
                      activateMutation.mutate(String(provider.provider_id ?? ''), {
                        onSuccess: () => {
                          setStatusTone('success');
                          setStatusMessage(`已激活提供商：${String(provider.provider_name ?? '')}`);
                        },
                        onError: (error) => {
                          setStatusTone('error');
                          setStatusMessage(error instanceof Error ? error.message : '激活失败，请稍后重试。');
                        },
                      });
                    }}>
                    激活
                  </button>
                )}
                <button type="button" className="btn btn-sm" disabled={testMutation.isPending}
                  onClick={() => {
                    clearStatus();
                    testMutation.mutate(String(provider.provider_id ?? ''), {
                      onSuccess: () => {
                        setStatusTone('success');
                        setStatusMessage(`连接测试成功：${String(provider.provider_name ?? '')}`);
                      },
                      onError: (error) => {
                        setStatusTone('error');
                        setStatusMessage(error instanceof Error ? error.message : '连接测试失败，请稍后重试。');
                      },
                    });
                  }}>
                  {testMutation.isPending ? '测试中…' : '测试连接'}
                </button>
                <button type="button" className="btn btn-sm btn-danger" disabled={deleteMutation.isPending}
                  onClick={() => handleDeleteProvider(provider)}>
                  {deleteMutation.isPending ? '删除中…' : '删除'}
                </button>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
