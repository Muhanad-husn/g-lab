import * as React from "react";
import { cn } from "@/lib/utils";

// ─── Simple toast implementation (no @radix-ui/react-toast needed in Phase 1) ─

function ToastProvider({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

function ToastViewport({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "fixed bottom-0 right-0 z-[100] flex max-h-screen w-full flex-col p-4 md:max-w-[420px]",
        className,
      )}
      {...props}
    />
  );
}

interface ToastProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "destructive";
}

function Toast({ className, variant = "default", ...props }: ToastProps) {
  return (
    <div
      className={cn(
        "group pointer-events-auto relative flex w-full items-center justify-between space-x-2 overflow-hidden rounded-md border p-4 pr-6 shadow-lg",
        variant === "default" && "border bg-background text-foreground",
        variant === "destructive" &&
          "border-destructive bg-destructive text-destructive-foreground",
        className,
      )}
      {...props}
    />
  );
}

function ToastTitle({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("text-sm font-semibold", className)} {...props} />;
}

function ToastDescription({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("text-sm opacity-90", className)} {...props} />;
}

function ToastClose({ className, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={cn(
        "absolute right-1 top-1 rounded-md p-1 text-xs opacity-0 transition-opacity group-hover:opacity-100",
        className,
      )}
      aria-label="Close"
      {...props}
    >
      ✕
    </button>
  );
}

export {
  ToastProvider,
  ToastViewport,
  Toast,
  ToastTitle,
  ToastDescription,
  ToastClose,
};
