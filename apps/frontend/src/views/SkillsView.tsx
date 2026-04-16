import { useState, useCallback } from 'react';
import { useOutletContext } from 'react-router';

import { electronClient } from '../lib/api/electron-client';

interface ContextType {
  localRootPath: string | null;
}

const defaultContext: ContextType = { localRootPath: null };

export interface LocalSkill {
  name: string;
  instruction: string;
  description: string;
  path: string;
}

export function SkillsView() {
  const ctx = useOutletContext<ContextType>() ?? defaultContext;
  const { localRootPath } = ctx;

  const [skills, setSkills] = useState<LocalSkill[]>([]);
  const [selectedSkill, setSelectedSkill] = useState<LocalSkill | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [editName, setEditName] = useState('');
  const [editInstruction, setEditInstruction] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [createMode, setCreateMode] = useState(false);
  const [newName, setNewName] = useState('');
  const [newInstruction, setNewInstruction] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadSkills = useCallback(async () => {
    if (!localRootPath) return;
    setLoading(true);
    setError(null);
    try {
      const skillsDir = 'skills';
      const result = await electronClient.readLocalDirectory({ rootPath: localRootPath, dirPath: skillsDir });
      const mdFiles = result.tree.filter(n => n.kind === 'file' && n.name.endsWith('.md'));
      const loaded: LocalSkill[] = [];
      for (const file of mdFiles) {
        try {
          const content = await electronClient.readLocalFile({ rootPath: localRootPath, filePath: `${skillsDir}/${file.name}` });
          const skill = parseSkillContent(content, file.name);
          loaded.push({ ...skill, path: `${skillsDir}/${file.name}` });
        } catch {
          // skip invalid files
        }
      }
      setSkills(loaded);
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [localRootPath]);

  // Load skills on mount if localRootPath is available
  if (localRootPath && skills.length === 0 && !loading && !error) {
    loadSkills();
  }

  function parseSkillContent(content: string, fileName: string): { name: string; instruction: string; description: string } {
    let name = fileName.replace(/\.md$/, '');
    let instruction = '';
    let description = '';

    const nameMatch = content.match(/^#\s*(.+)$/m);
    if (nameMatch) name = nameMatch[1].trim();

    const descMatch = content.match(/^description:\s*(.+)$/m);
    if (descMatch) description = descMatch[1].trim();

    // Instruction is everything after the first heading
    const firstHeading = content.search(/^#.+$/m);
    if (firstHeading !== -1) {
      instruction = content.slice(firstHeading).replace(/^#.+\n*/, '').trim();
    } else {
      instruction = content.trim();
    }

    return { name, instruction, description };
  }

  const handleSelect = (skill: LocalSkill) => {
    setSelectedSkill(skill);
    setEditName(skill.name);
    setEditInstruction(skill.instruction);
    setEditDescription(skill.description);
    setEditMode(false);
  };

  const handleSave = async () => {
    if (!selectedSkill || !localRootPath) return;
    const content = `description: ${editDescription}\n\n# ${editName}\n\n${editInstruction}`;
    await electronClient.saveLocalFile({ rootPath: localRootPath, filePath: selectedSkill.path, content });
    const updated = skills.map(s => s.path === selectedSkill.path
      ? { ...s, name: editName, instruction: editInstruction, description: editDescription }
      : s
    );
    setSkills(updated);
    setSelectedSkill({ ...selectedSkill, name: editName, instruction: editInstruction, description: editDescription });
    setEditMode(false);
  };

  const handleCreate = async () => {
    if (!localRootPath || !newName.trim()) return;
    const fileName = `${newName.trim().replace(/\s+/g, '_')}.md`;
    const content = `description: \n\n# ${newName.trim()}\n\n${newInstruction}`;
    await electronClient.createLocalFile({ rootPath: localRootPath, filePath: `skills/${fileName}` });
    await electronClient.saveLocalFile({ rootPath: localRootPath, filePath: `skills/${fileName}`, content });
    const skill: LocalSkill = { name: newName.trim(), instruction: newInstruction, description: '', path: `skills/${fileName}` };
    setSkills([...skills, skill]);
    setSelectedSkill(skill);
    setEditName(skill.name);
    setEditInstruction(skill.instruction);
    setEditDescription('');
    setCreateMode(false);
    setNewName('');
    setNewInstruction('');
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

  return (
    <div className="command-center">
      <section className="surface-panel">
        <button type="button" className="btn" onClick={() => setCreateMode(!createMode)}>
          {createMode ? '取消' : '新建技能'}
        </button>
        <button type="button" className="btn" onClick={loadSkills}>刷新</button>
        {createMode && (
          <form className="inline-form" onSubmit={(e) => { e.preventDefault(); handleCreate(); }}>
            <input type="text" className="form-input" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="名称" required />
            <textarea className="form-input" rows={3} value={newInstruction} onChange={(e) => setNewInstruction(e.target.value)} placeholder="指令" required />
            <button type="submit" className="btn btn-primary">创建</button>
          </form>
        )}
      </section>

      {loading && <section className="surface-panel"><p>加载中…</p></section>}
      {error && <section className="surface-panel surface-panel-error"><p>{error}</p></section>}

      <section className="surface-panel">
        <ul className="object-list">
          {skills.map((skill) => (
            <li key={skill.path} className={`object-item ${selectedSkill?.path === skill.path ? 'version-active' : ''}`}>
              <button type="button" className="skill-select-btn" onClick={() => handleSelect(skill)}>
                <strong>{skill.name}</strong>
                {skill.description && <span className="version-scope">{skill.description}</span>}
              </button>
            </li>
          ))}
        </ul>
      </section>

      {selectedSkill && (
        <section className="surface-panel">
          {editMode ? (
            <form className="inline-form" onSubmit={(e) => { e.preventDefault(); handleSave(); }}>
              <input type="text" className="form-input" value={editName} onChange={(e) => setEditName(e.target.value)} placeholder="名称" />
              <input type="text" className="form-input" value={editDescription} onChange={(e) => setEditDescription(e.target.value)} placeholder="描述" />
              <textarea className="form-input" rows={5} value={editInstruction} onChange={(e) => setEditInstruction(e.target.value)} placeholder="指令" />
              <div className="proposal-actions">
                <button type="submit" className="btn btn-primary">保存</button>
                <button type="button" className="btn" onClick={() => setEditMode(false)}>取消</button>
              </div>
            </form>
          ) : (
            <>
              <div className="version-instruction">{selectedSkill.instruction}</div>
              <div className="proposal-actions">
                <button type="button" className="btn" onClick={() => setEditMode(true)}>编辑</button>
              </div>
            </>
          )}
        </section>
      )}
    </div>
  );
}
