import { Badge } from "@/components/ui/badge";
import { PARSE_QUALITY_TIERS } from "@/lib/constants";
import type { ParseTier } from "@/lib/types";

const TIER_VARIANT: Record<ParseTier, "default" | "secondary" | "outline"> = {
  high: "default",
  standard: "secondary",
  basic: "outline",
  pending: "outline",
};

export function ParseTierBadge({ tier }: { tier: ParseTier | null }) {
  if (!tier) return null;
  const info = PARSE_QUALITY_TIERS[tier];
  return (
    <Badge variant={TIER_VARIANT[tier]} className="text-[9px] h-4 px-1">
      {info.label}
    </Badge>
  );
}
