/**
 * Toast container — renders transient notifications from monitoringSlice.
 *
 * Uses shadcn/ui Toast component. Mounted once in `App.tsx`.
 * Auto-dismisses after `toast.duration` ms (default 5000). Sticky if 0.
 */
import { useEffect, useRef } from "react";

import {
  Toast,
  ToastClose,
  ToastDescription,
  ToastProvider,
  ToastTitle,
  ToastViewport,
} from "@/components/ui/toast";
import { useStore } from "@/store";
import type { Toast as ToastData } from "@/store/monitoringSlice";

function toVariant(
  level: ToastData["level"],
): "default" | "destructive" | undefined {
  if (level === "error") return "destructive";
  return "default";
}

function ToastItem({ toast }: { toast: ToastData }) {
  const dismissToast = useStore((s) => s.dismissToast);
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    if (toast.duration > 0) {
      timerRef.current = setTimeout(() => {
        dismissToast(toast.id);
      }, toast.duration);
    }
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [toast.id, toast.duration, dismissToast]);

  return (
    <Toast variant={toVariant(toast.level)}>
      <div className="grid gap-1">
        <ToastTitle>{toast.title}</ToastTitle>
        {toast.message && <ToastDescription>{toast.message}</ToastDescription>}
      </div>
      <ToastClose onClick={() => dismissToast(toast.id)} />
    </Toast>
  );
}

export function ToastContainer() {
  const toasts = useStore((s) => s.toasts);

  return (
    <ToastProvider>
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} />
      ))}
      <ToastViewport />
    </ToastProvider>
  );
}
