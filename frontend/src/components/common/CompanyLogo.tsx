import { useEffect, useMemo, useState } from "react";
import type { Company } from "../../types";

type Props = {
  company: Pick<Company, "name" | "ticker" | "domain" | "color">;
  size?: number;
  radius?: number;
};

export default function CompanyLogo({
  company,
  size = 36,
  radius = 10,
}: Props) {
  const [sourceIndex, setSourceIndex] = useState(0);
  const logoSources = useMemo(() => {
    const domain = company.domain.trim();

    if (!domain) return [];

    const encodedDomain = encodeURIComponent(domain);

    return [
      `https://www.google.com/s2/favicons?domain=${encodedDomain}&sz=128`,
      `https://icons.duckduckgo.com/ip3/${domain}.ico`,
      `https://${domain}/favicon.ico`,
    ];
  }, [company.domain]);
  const logoUrl = logoSources[sourceIndex];
  const showLogo = Boolean(logoUrl);

  useEffect(() => {
    setSourceIndex(0);
  }, [company.domain]);

  return (
    <span
      className="flex shrink-0 items-center justify-center overflow-hidden"
      style={{
        width: size,
        height: size,
        borderRadius: radius,
        background: showLogo ? "#ffffff" : company.color,
      }}
    >
      {showLogo ? (
        <img
          key={`${company.domain}-${sourceIndex}`}
          src={logoUrl}
          alt={`${company.name} logo`}
          width={size}
          height={size}
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setSourceIndex((index) => index + 1)}
          className="h-full w-full object-contain"
          style={{ padding: size * 0.16 }}
        />
      ) : (
        <span
          className="font-bold text-canvas"
          style={{ fontSize: size * 0.34 }}
        >
          {company.ticker.slice(0, 2)}
        </span>
      )}
    </span>
  );
}
