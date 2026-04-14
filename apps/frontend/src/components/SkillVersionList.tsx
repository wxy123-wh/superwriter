import type { SkillWorkshopVersionSnapshot } from '../lib/api/client';

export function SkillVersionList({
  versions,
}: {
  versions: SkillWorkshopVersionSnapshot[];
}) {
  if (versions.length === 0) {
    return <p className="empty-copy">暂无版本记录。</p>;
  }

  return (
    <ul className="version-list">
      {versions.map((version) => (
        <li key={version.revision_id} className={`version-item ${version.is_active ? 'version-active' : ''}`}>
          <div className="version-info">
            <span className="version-number">rev {version.revision_number}</span>
            <strong>{version.name}</strong>
            {version.is_active && <span className="version-badge">激活</span>}
          </div>
          <p className="version-scope">{version.style_scope}</p>
          {version.instruction && (
            <details className="version-details">
              <summary>指令</summary>
              <pre className="version-instruction">{version.instruction}</pre>
            </details>
          )}
        </li>
      ))}
    </ul>
  );
}
