import type { Company, SignalLeader } from "../../types";
import DeltaBadge from "../common/DeltaBadge";
import CompanyLogo from "../common/CompanyLogo";

type Props = {
  leaders: SignalLeader[];
  onSelect: (company: Company) => void;
};

export default function SignalLeaders({ leaders, onSelect }: Props) {
  return (
    <section className="rounded-xl border border-hairline bg-surface p-5">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-faint">
        Signal leaders
      </p>
      <ul className="mt-2">
        {leaders.map((leader, i) => (
          <li
            key={leader.id}
            className={i > 0 ? "border-t border-hairline" : ""}
          >
            <button
              onClick={() => onSelect(leader.company)}
              className="flex w-full items-start gap-3 py-3.5 text-left transition hover:opacity-80"
            >
              <span className="mt-0.5">
                <CompanyLogo company={leader.company} size={32} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-semibold text-txt">
                  {leader.company.name}
                </span>
                <span className="block text-[13px] leading-snug text-muted">
                  {leader.insight}
                </span>
              </span>
              <DeltaBadge delta={leader.delta} deviation={leader.deviation} />
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
