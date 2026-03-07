import type { ReactNode } from "react";

interface SectionHeaderProps {
  children: ReactNode;
  count?: number;
}

export function SectionHeader({ children, count }: SectionHeaderProps) {
  return (
    <p className="px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
      {children}
      {count != null && ` (${count})`}
    </p>
  );
}
