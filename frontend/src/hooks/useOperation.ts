/**
 * Generic async operation wrapper hook.
 *
 * Manages per-component `isLoading` state and delegates toast/logging to the
 * API client and monitoringSlice (no duplication).
 *
 * Usage:
 * ```tsx
 * const { execute: expandNode, isLoading } = useOperation(
 *   (id: string, hops: number) => api.graph.expand({ node_ids: [id], hops }),
 *   { operationType: "neo4j.expand", operationLabel: "Expanding node..." },
 * );
 *
 * <button onClick={() => expandNode(nodeId, 2)} disabled={isLoading}>
 *   Expand
 * </button>
 * ```
 */
import { useCallback, useRef, useState } from "react";

import { useStore } from "@/store";

interface UseOperationOptions {
  /** Operation type key (e.g. "neo4j.expand"). Used for tracking. */
  operationType: string;
  /** Human-readable label shown while operation is in progress. */
  operationLabel: string;
}

interface UseOperationReturn<TArgs extends unknown[], TResult> {
  /** Call this to start the operation. Returns the result or throws. */
  execute: (...args: TArgs) => Promise<TResult>;
  /** `true` while the operation is in flight. */
  isLoading: boolean;
}

export function useOperation<TArgs extends unknown[], TResult>(
  fn: (...args: TArgs) => Promise<TResult>,
  options: UseOperationOptions,
): UseOperationReturn<TArgs, TResult> {
  const [isLoading, setIsLoading] = useState(false);
  const opIdRef = useRef<string | null>(null);

  const execute = useCallback(
    async (...args: TArgs): Promise<TResult> => {
      const { startOperation, endOperation } = useStore.getState();

      const opId = startOperation(
        options.operationType,
        options.operationLabel,
      );
      opIdRef.current = opId;
      setIsLoading(true);

      try {
        const result = await fn(...args);
        return result;
      } finally {
        setIsLoading(false);
        endOperation(opId);
        opIdRef.current = null;
      }
    },
    [fn, options.operationType, options.operationLabel],
  );

  return { execute, isLoading };
}
