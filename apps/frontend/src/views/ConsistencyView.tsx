/**
 * ConsistencyView
 * UI for managing chapter snapshots and checking consistency
 */

import { useState, useEffect } from 'react';
import { useLocation } from 'react-router';
import { readRouteSearch } from '../app/AppShell';
import { useChapterSnapshot } from '../hooks/useChapterSnapshot';
import type { ConsistencyIssue } from '../types/chapter-snapshot';

export function ConsistencyView() {
  const location = useLocation();
  const context = readRouteSearch(location.search);
  const projectId = context.projectId || '';

  const [selectedChapter, setSelectedChapter] = useState(1);
  const [chapterContent, setChapterContent] = useState('');

  const {
    snapshot,
    snapshots,
    issues,
    isLoading,
    error,
    load,
    save,
    extractAndSave,
    runConsistencyCheck,
    clearError,
  } = useChapterSnapshot(projectId, selectedChapter);

  useEffect(() => {
    if (projectId) {
      load(projectId, selectedChapter);
    }
  }, [projectId, selectedChapter, load]);

  const handleExtractAndSave = async () => {
    if (!chapterContent.trim()) {
      return;
    }
    await extractAndSave(projectId, selectedChapter, chapterContent);
  };

  const handleSaveSnapshot = async () => {
    if (!snapshot) return;
    await save(projectId, snapshot);
  };

  const getSeverityBadge = (severity: 'error' | 'warning') => {
    return severity === 'error' ? (
      <span className="badge badge-error">错误</span>
    ) : (
      <span className="badge badge-warning">警告</span>
    );
  };

  const getIssueTypeLabel = (type: ConsistencyIssue['type']) => {
    const labels: Record<ConsistencyIssue['type'], string> = {
      character_conflict: '角色冲突',
      location_conflict: '地点冲突',
      timeline_error: '时间线错误',
      object_missing: '对象缺失',
    };
    return labels[type] || type;
  };

  return (
    <div className="consistency-view">
      <header className="view-header">
        <h2>章节一致性检查</h2>
        <div className="header-actions">
          <select
            className="form-select"
            value={selectedChapter}
            onChange={(e) => setSelectedChapter(Number(e.target.value))}
          >
            {Array.from({ length: 20 }, (_, i) => i + 1).map((ch) => (
              <option key={ch} value={ch}>
                第 {ch} 章
              </option>
            ))}
          </select>
        </div>
      </header>

      {error && (
        <div className="alert alert-error">
          <span>{error}</span>
          <button className="btn-close" onClick={clearError}>x</button>
        </div>
      )}

      <div className="consistency-content">
        <section className="surface-panel">
          <h3>章节内容</h3>
          <textarea
            className="form-textarea"
            rows={8}
            value={chapterContent}
            onChange={(e) => setChapterContent(e.target.value)}
            placeholder="在此粘贴章节内容进行提取..."
          />
          <div className="panel-actions">
            <button
              className="btn btn-primary"
              onClick={handleExtractAndSave}
              disabled={isLoading || !chapterContent.trim()}
            >
              {isLoading ? '处理中...' : '提取并保存快照'}
            </button>
          </div>
        </section>

        <section className="surface-panel">
          <h3>当前快照</h3>
          {snapshot ? (
            <div className="snapshot-details">
              <div className="snapshot-meta">
                <span className="meta-item">
                  <strong>章节:</strong> {snapshot.chapterNumber}
                </span>
                <span className="meta-item">
                  <strong>标题:</strong> {snapshot.chapterTitle || '无标题'}
                </span>
                <span className="meta-item">
                  <strong>时间戳:</strong> {new Date(snapshot.timestamp).toLocaleString()}
                </span>
              </div>

              <div className="character-states">
                <h4>角色状态 ({snapshot.characterStates.length})</h4>
                {snapshot.characterStates.length > 0 ? (
                  <ul className="character-list">
                    {snapshot.characterStates.map((char) => (
                      <li key={char.characterId} className="character-item">
                        <span className="character-name">{char.name}</span>
                        <span className={`status-badge status-${char.status}`}>
                          {char.status}
                        </span>
                        {char.location && (
                          <span className="character-location">{char.location}</span>
                        )}
                        {char.emotionalState && char.emotionalState !== 'unknown' && (
                          <span className="character-emotion">{char.emotionalState}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="empty-state">尚未提取角色</p>
                )}
              </div>

              <div className="world-state">
                <h4>世界状态</h4>
                <div className="world-state-details">
                  <span>
                    <strong>时间线:</strong> {snapshot.worldState.currentTimeline || '未设置'}
                  </span>
                  <span>
                    <strong>进行中的冲突:</strong> {snapshot.worldState.activeConflicts.length}
                  </span>
                  <span>
                    <strong>已揭示的秘密:</strong> {snapshot.worldState.revealedSecrets.length}
                  </span>
                  <span>
                    <strong>待解决的谜团:</strong> {snapshot.worldState.pendingMysteries}
                  </span>
                </div>
              </div>

              <div className="panel-actions">
                <button
                  className="btn"
                  onClick={handleSaveSnapshot}
                  disabled={isLoading}
                >
                  更新快照
                </button>
              </div>
            </div>
          ) : (
            <p className="empty-state">该章节尚无快照</p>
          )}
        </section>

        <section className="surface-panel">
          <h3>问题 ({issues.length})</h3>
          {issues.length > 0 ? (
            <ul className="issues-list">
              {issues.map((issue, index) => (
                <li key={index} className={`issue-item issue-${issue.severity}`}>
                  <div className="issue-header">
                    {getSeverityBadge(issue.severity)}
                    <span className="issue-type">{getIssueTypeLabel(issue.type)}</span>
                    <span className="issue-chapter">第 {issue.chapter} 章</span>
                  </div>
                  <p className="issue-message">{issue.message}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="empty-state">未检测到问题</p>
          )}
          <div className="panel-actions">
            <button
              className="btn"
              onClick={() => runConsistencyCheck({ characters: [], locations: [], trackedObjects: [] })}
              disabled={!snapshot}
            >
              运行一致性检查
            </button>
          </div>
        </section>

        <section className="surface-panel">
          <h3>前一章节快照</h3>
          {snapshots.length > 0 ? (
            <ul className="snapshot-list">
              {snapshots
                .filter((s) => s.chapterNumber < selectedChapter)
                .sort((a, b) => b.chapterNumber - a.chapterNumber)
                .map((s) => (
                  <li key={s.chapterNumber} className="snapshot-item">
                    <button
                      className="snapshot-link"
                      onClick={() => setSelectedChapter(s.chapterNumber)}
                    >
                      第 {s.chapterNumber} 章
                      {s.chapterTitle && `: ${s.chapterTitle}`}
                    </button>
                    <span className="snapshot-time">
                      {new Date(s.timestamp).toLocaleDateString()}
                    </span>
                  </li>
                ))}
            </ul>
          ) : (
            <p className="empty-state">无前一快照</p>
          )}
        </section>
      </div>
    </div>
  );
}
