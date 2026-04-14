export function StartupView() {
  return (
    <div className="surface-panel" style={{ padding: '2rem' }}>
      <h2>欢迎使用 SuperWriter</h2>
      <p>请从侧边栏选择功能：</p>
      <ul>
        <li><strong>技能工坊</strong> — 管理写作风格规则</li>
        <li><strong>设置</strong> — 配置 AI 提供者</li>
      </ul>
    </div>
  );
}
