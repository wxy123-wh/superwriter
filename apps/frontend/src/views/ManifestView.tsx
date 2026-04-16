import { useState, useEffect } from 'react';
import { useOutletContext } from 'react-router';
import { useNovelManifest } from '../contexts/NovelManifestContext';
import type { Character } from '../types/novel-manifest';

type TabType = 'characters' | 'locations' | 'timeline' | 'objects';

interface CharacterFormData {
  name: string;
  role: Character['role'];
  aliases: string;
  appearance: string;
  personality: string;
  background: string;
  speechPatterns: string;
}

interface LocationFormData {
  name: string;
  description: string;
  rules: string;
}

interface TimelineFormData {
  date: string;
  event: string;
  chapter: string;
}

interface ObjectFormData {
  name: string;
  description: string;
}

const emptyCharacterForm: CharacterFormData = {
  name: '',
  role: 'supporting',
  aliases: '',
  appearance: '',
  personality: '',
  background: '',
  speechPatterns: '',
};

const emptyLocationForm: LocationFormData = {
  name: '',
  description: '',
  rules: '',
};

const emptyTimelineForm: TimelineFormData = {
  date: '',
  event: '',
  chapter: '',
};

const emptyObjectForm: ObjectFormData = {
  name: '',
  description: '',
};

export function ManifestView() {
  const context = useOutletContext<{ projectId: string | null }>();
  const {
    manifest,
    isLoading,
    error,
    addCharacter,
    updateCharacter,
    deleteCharacter,
    addLocation,
    deleteLocation,
    addTimelineEvent,
    deleteTimelineEvent,
    trackObject,
    deleteTrackedObject,
    reloadManifest,
  } = useNovelManifest();

  const [activeTab, setActiveTab] = useState<TabType>('characters');
  const [selectedCharacterId, setSelectedCharacterId] = useState<string | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  // Forms
  const [characterForm, setCharacterForm] = useState<CharacterFormData>(emptyCharacterForm);
  const [locationForm, setLocationForm] = useState<LocationFormData>(emptyLocationForm);
  const [timelineForm, setTimelineForm] = useState<TimelineFormData>(emptyTimelineForm);
  const [objectForm, setObjectForm] = useState<ObjectFormData>(emptyObjectForm);

  useEffect(() => {
    if (context.projectId) {
      reloadManifest(context.projectId);
    }
  }, [context.projectId, reloadManifest]);

  const handleAddCharacter = async () => {
    if (!characterForm.name.trim()) return;
    await addCharacter({
      name: characterForm.name,
      role: characterForm.role,
      aliases: characterForm.aliases ? characterForm.aliases.split(',').map(s => s.trim()) : [],
      appearance: characterForm.appearance || undefined,
      personality: characterForm.personality || undefined,
      background: characterForm.background || undefined,
      speechPatterns: characterForm.speechPatterns ? characterForm.speechPatterns.split(',').map(s => s.trim()) : [],
      relationships: [],
    });
    setCharacterForm(emptyCharacterForm);
    setShowAddForm(false);
  };

  const handleUpdateCharacter = async (id: string) => {
    await updateCharacter(id, {
      name: characterForm.name,
      role: characterForm.role,
      aliases: characterForm.aliases ? characterForm.aliases.split(',').map(s => s.trim()) : [],
      appearance: characterForm.appearance || undefined,
      personality: characterForm.personality || undefined,
      background: characterForm.background || undefined,
      speechPatterns: characterForm.speechPatterns ? characterForm.speechPatterns.split(',').map(s => s.trim()) : [],
    });
    setCharacterForm(emptyCharacterForm);
    setEditingId(null);
  };

  const handleEditCharacter = (char: Character) => {
    setCharacterForm({
      name: char.name,
      role: char.role,
      aliases: char.aliases?.join(', ') || '',
      appearance: char.appearance || '',
      personality: char.personality || '',
      background: char.background || '',
      speechPatterns: char.speechPatterns?.join(', ') || '',
    });
    setEditingId(char.id);
    setShowAddForm(true);
  };

  const handleAddLocation = async () => {
    if (!locationForm.name.trim()) return;
    await addLocation({
      name: locationForm.name,
      description: locationForm.description || undefined,
      rules: locationForm.rules ? locationForm.rules.split(',').map(s => s.trim()) : [],
    });
    setLocationForm(emptyLocationForm);
    setShowAddForm(false);
  };

  const handleAddTimelineEvent = async () => {
    if (!timelineForm.event.trim()) return;
    await addTimelineEvent({
      date: timelineForm.date || undefined,
      event: timelineForm.event,
      chapter: timelineForm.chapter ? parseInt(timelineForm.chapter) : undefined,
    });
    setTimelineForm(emptyTimelineForm);
    setShowAddForm(false);
  };

  const handleTrackObject = async () => {
    if (!objectForm.name.trim()) return;
    await trackObject({
      name: objectForm.name,
      description: objectForm.description || undefined,
    });
    setObjectForm(emptyObjectForm);
    setShowAddForm(false);
  };

  if (isLoading) {
    return <div className="manifest-view"><p>加载中...</p></div>;
  }

  if (error) {
    return <div className="manifest-view"><p className="error">错误: {error}</p></div>;
  }

  return (
    <div className="manifest-view">
      <div className="manifest-tabs">
        <button
          className={`manifest-tab ${activeTab === 'characters' ? 'active' : ''}`}
          onClick={() => setActiveTab('characters')}
        >
          角色 ({manifest.characters.length})
        </button>
        <button
          className={`manifest-tab ${activeTab === 'locations' ? 'active' : ''}`}
          onClick={() => setActiveTab('locations')}
        >
          地点 ({manifest.locations.length})
        </button>
        <button
          className={`manifest-tab ${activeTab === 'timeline' ? 'active' : ''}`}
          onClick={() => setActiveTab('timeline')}
        >
          时间线 ({manifest.timeline.length})
        </button>
        <button
          className={`manifest-tab ${activeTab === 'objects' ? 'active' : ''}`}
          onClick={() => setActiveTab('objects')}
        >
          物品 ({manifest.trackedObjects.length})
        </button>
      </div>

      <div className="manifest-content">
        {activeTab === 'characters' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>角色列表</h3>
              {!showAddForm && (
                <button className="btn btn-primary" onClick={() => { setShowAddForm(true); setEditingId(null); setCharacterForm(emptyCharacterForm); }}>
                  添加角色
                </button>
              )}
            </div>

            {showAddForm && (
              <div className="manifest-form">
                <h4>{editingId ? '编辑角色' : '新建角色'}</h4>
                <div className="form-group">
                  <label>名称 *</label>
                  <input
                    type="text"
                    className="form-input"
                    value={characterForm.name}
                    onChange={e => setCharacterForm(f => ({ ...f, name: e.target.value }))}
                    placeholder="角色名称"
                    required
                  />
                </div>
                <div className="form-group">
                  <label>角色类型</label>
                  <select
                    className="form-input"
                    value={characterForm.role}
                    onChange={e => setCharacterForm(f => ({ ...f, role: e.target.value as Character['role'] }))}
                  >
                    <option value="protagonist">主角</option>
                    <option value="antagonist">反派</option>
                    <option value="supporting">配角</option>
                    <option value="minor">龙套</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>别名（逗号分隔）</label>
                  <input
                    type="text"
                    className="form-input"
                    value={characterForm.aliases}
                    onChange={e => setCharacterForm(f => ({ ...f, aliases: e.target.value }))}
                    placeholder="别名1, 别名2"
                  />
                </div>
                <div className="form-group">
                  <label>外貌</label>
                  <textarea
                    className="form-input"
                    value={characterForm.appearance}
                    onChange={e => setCharacterForm(f => ({ ...f, appearance: e.target.value }))}
                    placeholder="外貌描述"
                    rows={2}
                  />
                </div>
                <div className="form-group">
                  <label>性格</label>
                  <textarea
                    className="form-input"
                    value={characterForm.personality}
                    onChange={e => setCharacterForm(f => ({ ...f, personality: e.target.value }))}
                    placeholder="性格特点"
                    rows={2}
                  />
                </div>
                <div className="form-group">
                  <label>背景</label>
                  <textarea
                    className="form-input"
                    value={characterForm.background}
                    onChange={e => setCharacterForm(f => ({ ...f, background: e.target.value }))}
                    placeholder="角色背景"
                    rows={2}
                  />
                </div>
                <div className="form-group">
                  <label>语言风格（逗号分隔）</label>
                  <input
                    type="text"
                    className="form-input"
                    value={characterForm.speechPatterns}
                    onChange={e => setCharacterForm(f => ({ ...f, speechPatterns: e.target.value }))}
                    placeholder="口头禅, 常用词"
                  />
                </div>
                <div className="form-actions">
                  {editingId ? (
                    <>
                      <button className="btn btn-primary" onClick={() => handleUpdateCharacter(editingId)}>保存</button>
                      <button className="btn" onClick={() => { setEditingId(null); setShowAddForm(false); }}>取消</button>
                    </>
                  ) : (
                    <>
                      <button className="btn btn-primary" onClick={handleAddCharacter}>添加</button>
                      <button className="btn" onClick={() => setShowAddForm(false)}>取消</button>
                    </>
                  )}
                </div>
              </div>
            )}

            <div className="manifest-list">
              {manifest.characters.length === 0 ? (
                <p className="empty-hint">暂无角色，点击"添加角色"开始</p>
              ) : (
                manifest.characters.map(char => (
                  <div
                    key={char.id}
                    className={`manifest-item ${selectedCharacterId === char.id ? 'selected' : ''}`}
                    onClick={() => setSelectedCharacterId(char.id === selectedCharacterId ? null : char.id)}
                  >
                    <div className="item-header">
                      <strong>{char.name}</strong>
                      <span className={`role-badge role-${char.role}`}>{char.role}</span>
                    </div>
                    {char.aliases && char.aliases.length > 0 && (
                      <div className="item-aliases">别名: {char.aliases.join(', ')}</div>
                    )}
                    {selectedCharacterId === char.id && (
                      <div className="item-details">
                        {char.appearance && <p><strong>外貌:</strong> {char.appearance}</p>}
                        {char.personality && <p><strong>性格:</strong> {char.personality}</p>}
                        {char.background && <p><strong>背景:</strong> {char.background}</p>}
                        {char.speechPatterns && char.speechPatterns.length > 0 && (
                          <p><strong>语言风格:</strong> {char.speechPatterns.join(', ')}</p>
                        )}
                        {char.relationships.length > 0 && (
                          <p><strong>关系:</strong> {char.relationships.length}个</p>
                        )}
                        <div className="item-actions">
                          <button className="btn btn-small" onClick={(e) => { e.stopPropagation(); handleEditCharacter(char); }}>编辑</button>
                          <button className="btn btn-small btn-danger" onClick={(e) => { e.stopPropagation(); deleteCharacter(char.id); }}>删除</button>
                        </div>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {activeTab === 'locations' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>地点列表</h3>
              {!showAddForm && (
                <button className="btn btn-primary" onClick={() => { setShowAddForm(true); setLocationForm(emptyLocationForm); }}>
                  添加地点
                </button>
              )}
            </div>

            {showAddForm && (
              <div className="manifest-form">
                <h4>新建地点</h4>
                <div className="form-group">
                  <label>名称 *</label>
                  <input
                    type="text"
                    className="form-input"
                    value={locationForm.name}
                    onChange={e => setLocationForm(f => ({ ...f, name: e.target.value }))}
                    placeholder="地点名称"
                    required
                  />
                </div>
                <div className="form-group">
                  <label>描述</label>
                  <textarea
                    className="form-input"
                    value={locationForm.description}
                    onChange={e => setLocationForm(f => ({ ...f, description: e.target.value }))}
                    placeholder="地点描述"
                    rows={2}
                  />
                </div>
                <div className="form-group">
                  <label>规则（逗号分隔）</label>
                  <input
                    type="text"
                    className="form-input"
                    value={locationForm.rules}
                    onChange={e => setLocationForm(f => ({ ...f, rules: e.target.value }))}
                    placeholder="规则1, 规则2"
                  />
                </div>
                <div className="form-actions">
                  <button className="btn btn-primary" onClick={handleAddLocation}>添加</button>
                  <button className="btn" onClick={() => setShowAddForm(false)}>取消</button>
                </div>
              </div>
            )}

            <div className="manifest-list">
              {manifest.locations.length === 0 ? (
                <p className="empty-hint">暂无地点，点击"添加地点"开始</p>
              ) : (
                manifest.locations.map(loc => (
                  <div key={loc.id} className="manifest-item">
                    <div className="item-header">
                      <strong>{loc.name}</strong>
                    </div>
                    {loc.description && <p className="item-desc">{loc.description}</p>}
                    {loc.rules && loc.rules.length > 0 && (
                      <p className="item-rules">规则: {loc.rules.join(', ')}</p>
                    )}
                    <div className="item-actions">
                      <button className="btn btn-small btn-danger" onClick={() => deleteLocation(loc.id)}>删除</button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {activeTab === 'timeline' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>时间线</h3>
              {!showAddForm && (
                <button className="btn btn-primary" onClick={() => { setShowAddForm(true); setTimelineForm(emptyTimelineForm); }}>
                  添加事件
                </button>
              )}
            </div>

            {showAddForm && (
              <div className="manifest-form">
                <h4>新建时间线事件</h4>
                <div className="form-group">
                  <label>日期</label>
                  <input
                    type="text"
                    className="form-input"
                    value={timelineForm.date}
                    onChange={e => setTimelineForm(f => ({ ...f, date: e.target.value }))}
                    placeholder="如: 第一年春天"
                  />
                </div>
                <div className="form-group">
                  <label>事件 *</label>
                  <textarea
                    className="form-input"
                    value={timelineForm.event}
                    onChange={e => setTimelineForm(f => ({ ...f, event: e.target.value }))}
                    placeholder="事件描述"
                    rows={2}
                    required
                  />
                </div>
                <div className="form-group">
                  <label>章节</label>
                  <input
                    type="number"
                    className="form-input"
                    value={timelineForm.chapter}
                    onChange={e => setTimelineForm(f => ({ ...f, chapter: e.target.value }))}
                    placeholder="章节号"
                  />
                </div>
                <div className="form-actions">
                  <button className="btn btn-primary" onClick={handleAddTimelineEvent}>添加</button>
                  <button className="btn" onClick={() => setShowAddForm(false)}>取消</button>
                </div>
              </div>
            )}

            <div className="manifest-list">
              {manifest.timeline.length === 0 ? (
                <p className="empty-hint">暂无时间线事件，点击"添加事件"开始</p>
              ) : (
                [...manifest.timeline]
                  .sort((a, b) => (a.chapter || 0) - (b.chapter || 0))
                  .map(evt => (
                    <div key={evt.id} className="manifest-item timeline-item">
                      <div className="item-header">
                        {evt.chapter && <span className="chapter-badge">第{evt.chapter}章</span>}
                        {evt.date && <span className="date-badge">{evt.date}</span>}
                      </div>
                      <p className="item-event">{evt.event}</p>
                      <div className="item-actions">
                        <button className="btn btn-small btn-danger" onClick={() => deleteTimelineEvent(evt.id)}>删除</button>
                      </div>
                    </div>
                  ))
              )}
            </div>
          </div>
        )}

        {activeTab === 'objects' && (
          <div className="tab-panel">
            <div className="panel-header">
              <h3>追踪物品</h3>
              {!showAddForm && (
                <button className="btn btn-primary" onClick={() => { setShowAddForm(true); setObjectForm(emptyObjectForm); }}>
                  添加物品
                </button>
              )}
            </div>

            {showAddForm && (
              <div className="manifest-form">
                <h4>新建追踪物品</h4>
                <div className="form-group">
                  <label>名称 *</label>
                  <input
                    type="text"
                    className="form-input"
                    value={objectForm.name}
                    onChange={e => setObjectForm(f => ({ ...f, name: e.target.value }))}
                    placeholder="物品名称"
                    required
                  />
                </div>
                <div className="form-group">
                  <label>描述</label>
                  <textarea
                    className="form-input"
                    value={objectForm.description}
                    onChange={e => setObjectForm(f => ({ ...f, description: e.target.value }))}
                    placeholder="物品描述"
                    rows={2}
                  />
                </div>
                <div className="form-actions">
                  <button className="btn btn-primary" onClick={handleTrackObject}>添加</button>
                  <button className="btn" onClick={() => setShowAddForm(false)}>取消</button>
                </div>
              </div>
            )}

            <div className="manifest-list">
              {manifest.trackedObjects.length === 0 ? (
                <p className="empty-hint">暂无追踪物品，点击"添加物品"开始</p>
              ) : (
                manifest.trackedObjects.map(obj => (
                  <div key={obj.id} className="manifest-item">
                    <div className="item-header">
                      <strong>{obj.name}</strong>
                    </div>
                    {obj.description && <p className="item-desc">{obj.description}</p>}
                    {obj.lastSeen && (
                      <p className="item-lastseen">
                        最后出现: 第{obj.lastSeen.chapter}章, {obj.lastSeen.location}
                      </p>
                    )}
                    <div className="item-actions">
                      <button className="btn btn-small btn-danger" onClick={() => deleteTrackedObject(obj.id)}>删除</button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
