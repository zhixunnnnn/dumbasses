import { useNavigation } from "../../navigation/NavigationContext";
import { na } from "../../lib/ui";

type Peer = { id: string; name: string; evidence_total: number | null };

/** Heat tint proportional to how far a value sits from the cohort average.
 *  Alpha is capped so a single outlier can't wash the whole column out. */
function tint(delta: number | null, spread: number): string | undefined {
  if (delta === null || spread <= 0) return undefined;
  const alpha = Math.min(0.16, (Math.abs(delta) / spread) * 0.16);
  return `rgb(var(--color-${delta >= 0 ? "pos" : "neg"}) / ${alpha.toFixed(3)})`;
}

export default function PeerTable({
  peers,
  selfId,
  selfName,
  selfTotal,
  sector,
}: {
  peers: Peer[];
  selfId: string;
  selfName: string;
  selfTotal: number | null;
  sector: string | null;
}) {
  const { navigate } = useNavigation();

  // The company itself is not always in `peers` — add it so the ranking is honest.
  const rows: Peer[] = peers.some((p) => p.id === selfId)
    ? [...peers]
    : [...peers, { id: selfId, name: selfName, evidence_total: selfTotal }];
  rows.sort((a, b) => (b.evidence_total ?? -Infinity) - (a.evidence_total ?? -Infinity));

  const scored = rows.map((r) => r.evidence_total).filter((v): v is number => v !== null);
  if (!scored.length) return null;
  const avg = scored.reduce((a, b) => a + b, 0) / scored.length;
  const spread = Math.max(...scored) - Math.min(...scored);
  const selfRank = rows.findIndex((r) => r.id === selfId) + 1;

  return (
    <div className="rounded-xl border border-hairline bg-surface shadow-panel">
      <div className="border-b border-hairline px-4 py-3">
        <h3 className="text-sm font-semibold text-txt">Sector peers</h3>
        <p className="text-[11px] text-faint">
          {sector ?? "Sector"} cohort · {scored.length} scored ·{" "}
          {selfRank > 0 ? `${selfName} ranks #${selfRank}` : "unranked"}. Shading is distance from
          the cohort average, not a judgement.
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] border-collapse text-[12px]">
          <thead>
            <tr className="border-b border-hairline text-[10px] uppercase tracking-wide text-faint">
              <th className="px-4 py-2 text-left font-medium">Company</th>
              <th className="px-4 py-2 text-right font-medium">Evidence</th>
              <th className="px-4 py-2 text-right font-medium">vs avg</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const isSelf = p.id === selfId;
              const delta = p.evidence_total === null ? null : p.evidence_total - avg;
              return (
                <tr
                  key={p.id}
                  onClick={() => !isSelf && navigate({ name: "evidenceCompany", id: p.id })}
                  className={`border-b border-hairline/50 transition ${
                    isSelf ? "bg-raised/60" : "cursor-pointer hover:bg-raised/40"
                  }`}
                >
                  <td className="px-4 py-2">
                    <span className={isSelf ? "font-semibold text-txt" : "text-muted"}>{p.name}</span>
                    {isSelf && (
                      <span className="ml-2 rounded border border-pos/30 px-1 py-0.5 text-[9px] font-semibold uppercase text-pos">
                        this
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-right font-mono text-txt"
                    style={{ backgroundColor: tint(delta, spread) }}>
                    {na(p.evidence_total)}
                  </td>
                  <td className="px-4 py-2 text-right font-mono"
                    style={{ color: delta === null ? undefined : `rgb(var(--color-${delta >= 0 ? "pos" : "neg"}))` }}>
                    {delta === null ? "—" : `${delta >= 0 ? "+" : ""}${delta.toFixed(1)}`}
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr className="border-t border-hairline text-faint">
              <td className="px-4 py-2 text-[11px] font-medium uppercase tracking-wide">Cohort average</td>
              <td className="px-4 py-2 text-right font-mono text-muted">{avg.toFixed(1)}</td>
              <td className="px-4 py-2 text-right font-mono">—</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
