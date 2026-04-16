interface TitleBarProps {
  title?: string;
}

export function TitleBar({ title = 'SuperWriter' }: TitleBarProps) {
  return (
    <header className="title-bar">
      <div className="title-bar-title">{title}</div>
    </header>
  );
}
