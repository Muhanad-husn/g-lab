export function PropertyTable({
  properties,
}: {
  properties: Record<string, unknown>;
}) {
  const entries = Object.entries(properties);

  if (entries.length === 0) {
    return (
      <p className="text-xs text-muted-foreground px-3 py-2">No properties</p>
    );
  }

  return (
    <table className="w-full text-xs">
      <tbody>
        {entries.map(([key, value]) => (
          <tr
            key={key}
            className="border-b border-border last:border-0 even:bg-muted/5"
          >
            <td className="px-3 py-1.5 font-mono text-[11px] font-medium text-muted-foreground w-1/3 align-top">
              {key}
            </td>
            <td className="px-3 py-1.5 text-foreground break-words">
              {value === null ? (
                <span className="text-muted-foreground italic">null</span>
              ) : (
                String(value)
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
