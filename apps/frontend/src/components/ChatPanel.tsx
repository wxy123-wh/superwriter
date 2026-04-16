import { useState, useCallback, useRef, useEffect } from 'react';
import { apiClient } from '../lib/api/client';
import { isElectron, electronClient } from '../lib/api/electron-client';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

interface ChatPanelProps {
  projectId: string | null;
  novelId: string | null;
}

export function ChatPanel({ projectId, novelId }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [chatSending, setChatSending] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const hasProject = !!(projectId && novelId);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleChatSend = useCallback(async () => {
    if (!chatInput.trim() || !projectId || !novelId) return;
    const msg = chatInput.trim();
    setChatInput('');
    setMessages((prev) => [...prev, { role: 'user', content: msg }]);
    setChatSending(true);
    setError(null);
    try {
      let res;
      if (isElectron()) {
        res = await electronClient.sendChat({
          projectId,
          novelId,
          params: {
            project_id: projectId,
            novel_id: novelId,
            workbench_type: 'editor-chat',
            user_message: msg,
            session_id: sessionId,
          },
        });
      } else {
        res = await apiClient.sendChat({
          projectId,
          novelId,
          params: {
            project_id: projectId,
            novel_id: novelId,
            workbench_type: 'editor-chat',
            user_message: msg,
            session_id: sessionId,
          },
        });
      }
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
  }, [chatInput, projectId, novelId, sessionId]);

  if (!hasProject) {
    return (
      <div className="panel-empty">
        选择项目后即可使用 AI 对话
      </div>
    );
  }

  return (
    <>
      <div className="panel-content">
        {messages.length === 0 && (
          <div className="panel-empty" style={{ marginTop: 60 }}>
            输入消息开始对话
          </div>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`chat-message ${m.role === 'user' ? 'user' : 'assistant'}`}
          >
            {m.content}
          </div>
        ))}
        {chatSending && (
          <div className="chat-message assistant">
            思考中…
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>
      {error && <div className="panel-content" style={{ color: '#f48771', fontSize: 12 }}>{error}</div>}
      <div className="panel-input">
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
        />
        <button
          className="btn btn-primary"
          onClick={handleChatSend}
          disabled={chatSending || !chatInput.trim() || !hasProject}
          style={{ alignSelf: 'flex-end' }}
        >
          <span className="codicon codicon-send" style={{ marginRight: 4 }}></span>
          发送
        </button>
      </div>
    </>
  );
}
