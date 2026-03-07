import type { ReactNode } from "react";

interface PanelHeaderProps {
  title: string;
  children?: ReactNode;
}

export function PanelHeader({ title, children }: PanelHeaderProps) {
  return (
    <div className="h-9 flex items-center px-3 border-b border-border shrink-0">
      <span className="text-xs font-semibold text-foreground">{title}</span>
      {children && <div className="ml-auto flex items-center gap-1.5">{children}</div>}
    </div>
  );
}
