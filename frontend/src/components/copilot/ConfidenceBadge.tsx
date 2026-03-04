import { CONFIDENCE_BANDS } from "@/lib/constants";
import type { ConfidenceScore } from "@/lib/types";

interface ConfidenceBadgeProps {
  confidence: ConfidenceScore;
}

const BAND_STYLES: Record<ConfidenceScore["band"], string> = {
  high: "bg-green-500/20 text-green-400 border-green-500/40",
  medium: "bg-yellow-500/20 text-yellow-400 border-yellow-500/40",
  low: "bg-red-500/20 text-red-400 border-red-500/40",
};

const BAND_DESCRIPTIONS: Record<ConfidenceScore["band"], string> = {
  high: `High confidence (≥${CONFIDENCE_BANDS.HIGH.threshold * 100}%) — answer is well-supported by graph data.`,
  medium: `Medium confidence (≥${CONFIDENCE_BANDS.MEDIUM.threshold * 100}%) — partial graph support; verify manually.`,
  low: `Low confidence (<${CONFIDENCE_BANDS.MEDIUM.threshold * 100}%) — limited graph evidence; treat with caution.`,
};

export function ConfidenceBadge({ confidence }: ConfidenceBadgeProps) {
  const label = CONFIDENCE_BANDS[confidence.band.toUpperCase() as keyof typeof CONFIDENCE_BANDS]?.label ?? confidence.band;
  const pct = Math.round(confidence.score * 100);

  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px] font-medium ${BAND_STYLES[confidence.band]}`}
      title={BAND_DESCRIPTIONS[confidence.band]}
    >
      {label} {pct}%
    </span>
  );
}
