import { useState } from 'react';
import { useSuspenseQuery } from '@tanstack/react-query';
import { useLocation } from 'react-router';

import { readRouteSearch } from '../app/AppShell';
import { skillsOptions } from '../app/router';
import { useUpsertSkill, useImportSkill } from '../lib/api/mutations';

export function SkillsView() {
  const location = useLocation();
  const context = readRouteSearch(location.search);
  const { data } = useSuspenseQuery(skillsOptions(context));
  const workshop = data.workshop;

  const upsertMutation = useUpsertSkill({
    projectId: context.projectId ?? '',
    novelId: context.novelId ?? '',
  });

  const importMutation = useImportSkill({
    projectId: context.projectId ?? '',
    novelId: context.novelId ?? '',
  });

  const [selectedSkillId, setSelectedSkillId] = useState<string | null>(
    workshop.selected_skill?.object_id ?? null,
  );
  const [editMode, setEditMode] = useState(false);
  const [editName, setEditName] = useState('');
  const [editInstruction, setEditInstruction] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [createMode, setCreateMode] = useState(false);
  const [newName, setNewName] = useState('');
  const [newInstruction, setNewInstruction] = useState('');
  const [importMode, setImportMode] = useState(false);
  const [importName, setImportName] = useState('');
  const [importInstruction, setImportInstruction] = useState('');

  const selectedSkill = workshop.skills.find((s) => s.object_id === selectedSkillId);

  const handleEdit = () => {
    if (!selectedSkill) return;
    setEditName(selectedSkill.name);
    setEditInstruction(selectedSkill.instruction);
    setEditDescription(selectedSkill.description);
    setEditMode(true);
  };

  const handleSave = () => {
    if (!selectedSkill) return;
    upsertMutation.mutate(
      {
        action: 'update',
        skill_object_id: selectedSkill.object_id,
        name: editName,
        instruction: editInstruction,
        description: editDescription,
      },
      {
        onSuccess: () => setEditMode(false),
      },
    );
  };

  const handleCreate = () => {
    upsertMutation.mutate(
      {
        action: 'create',
        name: newName,
        instruction: newInstruction,
      },
      {
        onSuccess: () => {
          setCreateMode(false);
          setNewName('');
          setNewInstruction('');
        },
      },
    );
  };

  const handleImport = () => {
    importMutation.mutate(
      { name: importName, instruction: importInstruction, donor_kind: 'prompt_template' },
      {
        onSuccess: () => {
          setImportMode(false);
          setImportName('');
          setImportInstruction('');
        },
      },
    );
  };

  return (
    <div className="command-center">
      <section className="surface-panel">
        <button type="button" className="btn" onClick={() => setCreateMode(!createMode)}>
          {createMode ? '取消' : '新建技能'}
        </button>
        <button type="button" className="btn" onClick={() => setImportMode(!importMode)}>
          {importMode ? '取消' : '导入技能'}
        </button>
        {createMode && (
          <form className="inline-form" onSubmit={(e) => { e.preventDefault(); handleCreate(); }}>
            <input type="text" className="form-input" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="名称" required />
            <textarea className="form-input" rows={3} value={newInstruction} onChange={(e) => setNewInstruction(e.target.value)} placeholder="指令" required />
            <button type="submit" className="btn btn-primary" disabled={upsertMutation.isPending}>
              {upsertMutation.isPending ? '创建中…' : '创建'}
            </button>
          </form>
        )}
        {importMode && (
          <form className="inline-form" onSubmit={(e) => { e.preventDefault(); handleImport(); }}>
            <input type="text" className="form-input" value={importName} onChange={(e) => setImportName(e.target.value)} placeholder="名称" required />
            <textarea className="form-input" rows={3} value={importInstruction} onChange={(e) => setImportInstruction(e.target.value)} placeholder="指令" required />
            <button type="submit" className="btn btn-primary" disabled={importMutation.isPending}>
              {importMutation.isPending ? '导入中…' : '导入'}
            </button>
          </form>
        )}
      </section>

      <section className="surface-panel">
        <ul className="object-list">
          {workshop.skills.map((skill) => (
            <li key={skill.object_id} className={`object-item ${selectedSkillId === skill.object_id ? 'version-active' : ''}`}>
              <button type="button" className="skill-select-btn" onClick={() => setSelectedSkillId(skill.object_id)}>
                <strong>{skill.name}</strong>
                <span className="version-scope">{skill.style_scope}</span>
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
                <button type="submit" className="btn btn-primary" disabled={upsertMutation.isPending}>
                  {upsertMutation.isPending ? '保存中…' : '保存'}
                </button>
                <button type="button" className="btn" onClick={() => setEditMode(false)}>取消</button>
              </div>
            </form>
          ) : (
            <>
              <div className="version-instruction">{selectedSkill.instruction}</div>
              <div className="proposal-actions">
                <button type="button" className="btn" onClick={handleEdit}>编辑</button>
              </div>
            </>
          )}
        </section>
      )}

    </div>
  );
}
