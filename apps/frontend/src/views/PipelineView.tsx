import { useState, useCallback } from 'react';
import { useLocation } from 'react-router';
import { readRouteSearch } from '../app/AppShell';
import { apiClient } from '../lib/api/client';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export function PipelineView() {
  const location = useLocation();
  const context = readRouteSearch(location.search);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [chatSending, setChatSending] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [error, setError] = useState<string | null>(null);

  const handleChatSend = useCallback(async () => {
    if (!chatInput.trim() || !context.projectId || !context.novelId) return;
    const msg = chatInput.trim();
    setChatInput('');
    setMessages((prev) => [...prev, { role: 'user', content: msg }]);
    setChatSending(true);
    setError(null);
    try {
      const res = await apiClient.sendChat({
        projectId: context.projectId,
        novelId: context.novelId,
        params: {
          project_id: context.projectId,
          novel_id: context.novelId,
          workbench_type: 'pipeline',
          user_message: msg,
          session_id: sessionId,
        },
      });
      setSessionId(res.session_id);
      setMessages((prev) => [...prev, { role: 'assistant', content: res.assistant_content }]);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `错误: ${e instanceof Error ? e.message : String(e)}` },
      ]);
    } finally {
      setChatSending(false);
    }
  }, [chatInput, context.projectId, context.novelId, sessionId]);

  return (
    <div className="surface-panel" style={{ padding: '2rem' }}>
      <h2>AI 对话台</h2>
      <p style={{ color: '#666', marginBottom: '1rem' }}>
        当前项目：{context.projectId ?? '未选择'} / {context.novelId ?? '未选择'}
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', maxWidth: 600 }}>
        <div style={{ minHeight: 200, border: '1px solid #ddd', borderRadius: 8, padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {messages.length === 0 && (
            <div style={{ color: '#bbb', textAlign: 'center', marginTop: 60 }}>
              输入消息开始对话
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} style={{
              padding: '0.5rem 0.75rem',
              borderRadius: 8,
              background: m.role === 'user' ? '#e3f2fd' : '#f5f5f5',
              alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
              maxWidth: '80%',
            }}>
              {m.content}
            </div>
          ))}
        </div>
        {error && <div style={{ color: '#c0392b', fontSize: 13 }}>{error}</div>}
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <textarea
            value={chatInput}
            onChange={(e) => setChatInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleChatSend();
              }
            }}
            placeholder="输入消息…"
            disabled={chatSending}
            style={{ flex: 1, resize: 'vertical', minHeight: 40 }}
          />
          <button
            className="btn btn-primary"
            onClick={handleChatSend}
            disabled={chatSending || !chatInput.trim() || !context.projectId || !context.novelId}
          >
            {chatSending ? '发送中…' : '发送'}
          </button>
        </div>
      </div>
    </div>
  );
}
