import { useRef } from 'react';
// @ts-ignore
import Editor, { type OnMount, type OnChange } from '@monaco-editor/react';
// @ts-ignore
import type { editor } from 'monaco-editor';

export interface MonacoEditorProps {
  value: string;
  onChange: (value: string) => void;
  language?: string;
  readOnly?: boolean;
  onCursorChange?: (line: number, column: number) => void;
}

export function MonacoEditor({
  value,
  onChange,
  language = 'markdown',
  readOnly = false,
  onCursorChange,
}: MonacoEditorProps) {
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);

  const handleMount: OnMount = (editor) => {
    editorRef.current = editor;
    editor.focus();
    editor.onDidChangeCursorPosition((e) => {
      onCursorChange?.(e.position.lineNumber, e.position.column);
    });
  };

  const handleChange: OnChange = (newValue) => {
    onChange(newValue ?? '');
  };

  return (
    <div className="monaco-wrapper">
      <Editor
        height="100%"
        language={language}
        value={value}
        onChange={handleChange}
        onMount={handleMount}
        options={{
          readOnly,
          minimap: { enabled: false },
          lineNumbers: 'on',
          wordWrap: 'on',
          fontSize: 14,
          padding: { top: 16 },
          scrollBeyondLastLine: false,
          automaticLayout: true,
          tabSize: 2,
        }}
        theme="vs-dark"
        loading={<div className="monaco-loading">加载编辑器…</div>}
      />
    </div>
  );
}
