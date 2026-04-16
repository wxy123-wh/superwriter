import { useState } from 'react';
import { useLocation } from 'react-router';
import { readRouteSearch } from '../app/AppShell';
import { useForeshadows } from '../hooks/useForeshadows';
import type { ForeshadowStatus, ForeshadowImportance } from '../types/foreshadow';

const STATUS_COLORS: Record<ForeshadowStatus, string> = {
  pending: '#f0c800',
  resolved: '#28a745',
  abandoned: '#6c757d',
};

const STATUS_LABELS: Record<ForeshadowStatus, string> = {
  pending: '待回收',
  resolved: '已回收',
  abandoned: '已废弃',
};

const IMPORTANCE_COLORS: Record<ForeshadowImportance, string> = {
  high: '#dc3545',
  medium: '#fd7e14',
  low: '#17a2b8',
};

export function ForeshadowView() {
  const location = useLocation();
  const context = readRouteSearch(location.search);
  const projectId = context.projectId ?? '';

  const { foreshadows, add, resolve, abandon, remove, isLoading, error } = useForeshadows(projectId);

  const [showModal, setShowModal] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState<ForeshadowStatus | 'all'>('all');
  const [filterChapter, _setFilterChapter] = useState<number | 'all'>('all');

  // Form state
  const [formTitle, setFormTitle] = useState('');
  const [formDescription, setFormDescription] = useState('');
  const [formImportance, setFormImportance] = useState<ForeshadowImportance>('medium');
  const [formPlantedChapter, setFormPlantedChapter] = useState(1);
  const [formKeywords, setFormKeywords] = useState('');

  // Resolve modal state
  const [resolveId, setResolveId] = useState<string | null>(null);
  const [resolveChapter, setResolveChapter] = useState(1);

  const filteredForeshadows = foreshadows.filter(f => {
    if (filterStatus !== 'all' && f.status !== filterStatus) return false;
    if (filterChapter !== 'all' && f.plantedChapter !== filterChapter) return false;
    return true;
  });

  const handleAdd = () => {
    setFormTitle('');
    setFormDescription('');
    setFormImportance('medium');
    setFormPlantedChapter(1);
    setFormKeywords('');
    setShowModal(true);
  };

  const handleSubmit = async () => {
    if (!formTitle.trim()) return;
    await add({
      title: formTitle.trim(),
      description: formDescription.trim(),
      importance: formImportance,
      plantedChapter: formPlantedChapter,
      keywords: formKeywords.split(',').map(k => k.trim()).filter(Boolean),
    });
    setShowModal(false);
  };

  const handleResolve = async () => {
    if (!resolveId) return;
    await resolve(resolveId, resolveChapter);
    setResolveId(null);
  };

  const handleAbandon = async (id: string) => {
    if (window.confirm('确定要废弃此伏笔吗？')) {
      await abandon(id);
    }
  };

  const handleDelete = async (id: string) => {
    if (window.confirm('确定要删除此伏笔吗？')) {
      await remove(id);
    }
  };

  if (isLoading) {
    return <div className="panel-empty">加载中...</div>;
  }

  if (error) {
    return <div className="panel-empty" style={{ color: '#dc3545' }}>{error}</div>;
  }

  return (
    <div className="foreshadow-view">
      <header className="view-header">
        <h2>伏笔追踪</h2>
        <div className="header-actions">
          <select
            className="form-input"
            value={filterStatus}
            onChange={e => setFilterStatus(e.target.value as ForeshadowStatus | 'all')}
          >
            <option value="all">全部状态</option>
            <option value="pending">待回收</option>
            <option value="resolved">已回收</option>
            <option value="abandoned">已废弃</option>
          </select>
          <button type="button" className="btn btn-primary" onClick={handleAdd}>
            添加伏笔
          </button>
        </div>
      </header>

      <div className="foreshadow-list">
        {filteredForeshadows.length === 0 ? (
          <div className="panel-empty">暂无伏笔</div>
        ) : (
          filteredForeshadows.map(f => (
            <div
              key={f.id}
              className={`foreshadow-item ${expandedId === f.id ? 'expanded' : ''}`}
            >
              <div className="foreshadow-summary" onClick={() => setExpandedId(expandedId === f.id ? null : f.id)}>
                <div className="foreshadow-badges">
                  <span
                    className="status-badge"
                    style={{ backgroundColor: STATUS_COLORS[f.status] }}
                  >
                    {STATUS_LABELS[f.status]}
                  </span>
                  <span
                    className="importance-badge"
                    style={{ backgroundColor: IMPORTANCE_COLORS[f.importance] }}
                  >
                    {f.importance === 'high' ? '高' : f.importance === 'medium' ? '中' : '低'}
                  </span>
                </div>
                <h3 className="foreshadow-title">{f.title}</h3>
                <div className="foreshadow-meta">
                  <span>种植于第{f.plantedChapter}章</span>
                  {f.resolvedChapter && <span>，回收于第{f.resolvedChapter}章</span>}
                </div>
              </div>

              {expandedId === f.id && (
                <div className="foreshadow-details">
                  {f.description && <p className="foreshadow-description">{f.description}</p>}
                  {f.keywords.length > 0 && (
                    <div className="foreshadow-keywords">
                      {f.keywords.map((kw, i) => (
                        <span key={i} className="keyword-tag">{kw}</span>
                      ))}
                    </div>
                  )}
                  <div className="foreshadow-actions">
                    {f.status === 'pending' && (
                      <>
                        <button
                          type="button"
                          className="btn btn-primary"
                          onClick={() => {
                            setResolveId(f.id);
                            setResolveChapter(f.plantedChapter + 1);
                          }}
                        >
                          回收
                        </button>
                        <button
                          type="button"
                          className="btn"
                          onClick={() => handleAbandon(f.id)}
                        >
                          废弃
                        </button>
                      </>
                    )}
                    <button
                      type="button"
                      className="btn"
                      style={{ color: '#dc3545' }}
                      onClick={() => handleDelete(f.id)}
                    >
                      删除
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Add Modal */}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <h3>添加伏笔</h3>
            <form onSubmit={e => { e.preventDefault(); handleSubmit(); }}>
              <div className="form-group">
                <label>标题</label>
                <input
                  type="text"
                  className="form-input"
                  value={formTitle}
                  onChange={e => setFormTitle(e.target.value)}
                  placeholder="伏笔标题"
                  required
                />
              </div>
              <div className="form-group">
                <label>描述</label>
                <textarea
                  className="form-input"
                  rows={3}
                  value={formDescription}
                  onChange={e => setFormDescription(e.target.value)}
                  placeholder="详细描述..."
                />
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>重要程度</label>
                  <select
                    className="form-input"
                    value={formImportance}
                    onChange={e => setFormImportance(e.target.value as ForeshadowImportance)}
                  >
                    <option value="high">高</option>
                    <option value="medium">中</option>
                    <option value="low">低</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>种植章节</label>
                  <input
                    type="number"
                    className="form-input"
                    min={1}
                    value={formPlantedChapter}
                    onChange={e => setFormPlantedChapter(parseInt(e.target.value) || 1)}
                  />
                </div>
              </div>
              <div className="form-group">
                <label>关键词（逗号分隔）</label>
                <input
                  type="text"
                  className="form-input"
                  value={formKeywords}
                  onChange={e => setFormKeywords(e.target.value)}
                  placeholder="关键词1, 关键词2"
                />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn" onClick={() => setShowModal(false)}>
                  取消
                </button>
                <button type="submit" className="btn btn-primary">
                  添加
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Resolve Modal */}
      {resolveId && (
        <div className="modal-overlay" onClick={() => setResolveId(null)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <h3>回收伏笔</h3>
            <form onSubmit={e => { e.preventDefault(); handleResolve(); }}>
              <div className="form-group">
                <label>回收章节</label>
                <input
                  type="number"
                  className="form-input"
                  min={1}
                  value={resolveChapter}
                  onChange={e => setResolveChapter(parseInt(e.target.value) || 1)}
                />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn" onClick={() => setResolveId(null)}>
                  取消
                </button>
                <button type="submit" className="btn btn-primary">
                  确认回收
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
