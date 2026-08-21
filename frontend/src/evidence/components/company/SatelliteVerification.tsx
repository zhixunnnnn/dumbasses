import { useState } from "react";
import { ExternalLink, Globe, Layers, MapPin, Satellite } from "lucide-react";
import type { SiteObservation } from "../../types";
import { api, useApi } from "../../lib/api";

/**
 * Ground-truth panel: did the physical asset actually get built?
 *
 * Colour discipline is deliberate. Only "Observed" is coloured. "Not observed" and
 * "Inconclusive" stay neutral, because cloud cover, a stale outline and phased
 * construction all look identical to "they did not build it" — and rendering that in red
 * would state something the engine explicitly refuses to claim.
 */

const IMG = (rel: string) => `/api/satellite/image/${rel.split("/").pop()}`;

type Verdict = { label: string; className: string };

function verdictOf(changed: boolean | null): Verdict {
  if (changed === true)
    return { label: "OBSERVED", className: "border-pos/40 bg-pos/10 text-pos" };
  if (changed === false)
    return { label: "NOT OBSERVED", className: "border-hairline bg-raised/50 text-muted" };
  return { label: "INCONCLUSIVE", className: "border-hairline bg-raised/50 text-faint" };
}

function Scene({ label, scene }: { label: string; scene: SiteObservation["before"] }) {
  if (!scene?.image_path) {
    return (
      <div className="flex aspect-square items-center justify-center rounded-md border border-dashed border-hairline bg-raised/30 px-3 text-center text-[10px] text-faint">
        No low-cloud scene for {label.toLowerCase()}
      </div>
    );
  }
  return (
    <figure className="min-w-0">
      <img
        src={IMG(scene.image_path)}
        alt={`${label} — Sentinel-2 ${scene.date}`}
        loading="lazy"
        className="aspect-square w-full rounded-md border border-hairline object-cover"
      />
      <figcaption className="mt-1 text-[10px] text-faint">
        <span className="font-semibold text-muted">{label}</span> · {scene.date}
        {scene.cloud_cover != null && ` · ${scene.cloud_cover.toFixed(0)}% cloud`}
      </figcaption>
    </figure>
  );
}

function MapLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 rounded-md border border-hairline bg-canvas/40 px-2 py-1 text-[10px] text-muted transition hover:border-pos/40 hover:text-txt"
    >
      {children}
      <ExternalLink size={9} />
    </a>
  );
}

function SiteCard({ obs }: { obs: SiteObservation }) {
  const [view, setView] = useState<"detail" | "compare">("detail");
  const verdict = verdictOf(obs.changed);
  const { site } = obs;
  const links = obs.map_links;

  return (
    <div className="rounded-lg border border-hairline bg-canvas/30 p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-[12.5px] font-medium text-txt">
            {site.name || "Unnamed asset"}
          </p>
          <p className="mt-0.5 text-[10px] text-faint">
            {site.asset_type || "unknown type"}
            {site.operator && ` · ${site.operator}`} · {site.lat.toFixed(4)}, {site.lon.toFixed(4)}
          </p>
        </div>
        <span
          className={`shrink-0 rounded border px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide ${verdict.className}`}
        >
          {verdict.label}
        </span>
      </div>

      {(obs.detail_image || obs.before || obs.after) && (
        <div className="mt-2.5 flex gap-1">
          {obs.detail_image && (
            <button
              onClick={() => setView("detail")}
              className={`rounded px-2 py-0.5 text-[10px] transition ${
                view === "detail"
                  ? "bg-raised text-txt"
                  : "text-faint hover:text-muted"
              }`}
            >
              <MapPin size={9} className="mr-1 inline" />
              Detail
            </button>
          )}
          <button
            onClick={() => setView("compare")}
            className={`rounded px-2 py-0.5 text-[10px] transition ${
              view === "compare" ? "bg-raised text-txt" : "text-faint hover:text-muted"
            }`}
          >
            <Layers size={9} className="mr-1 inline" />
            Before / after
          </button>
        </div>
      )}

      <div className="mt-2">
        {view === "detail" && obs.detail_image ? (
          <figure>
            <img
              src={IMG(obs.detail_image)}
              alt={`${site.name} — high-resolution view`}
              loading="lazy"
              className="w-full rounded-md border border-hairline"
            />
            <figcaption className="mt-1 text-[10px] text-faint">
              Yellow outline is the registry footprint we measured.
              {obs.detail_attribution && ` Imagery: ${obs.detail_attribution}.`} Undated —
              shown so you can recognise the site, not to date it.
            </figcaption>
          </figure>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            <Scene label="Before" scene={obs.before} />
            <Scene label="After" scene={obs.after} />
          </div>
        )}
      </div>

      <p className="mt-2 text-[11px] leading-snug text-muted">{obs.note}</p>

      <div className="mt-2 flex flex-wrap gap-1.5">
        {site.registry_url && (
          <MapLink href={site.registry_url}>
            <MapPin size={9} /> OpenStreetMap
          </MapLink>
        )}
        {links?.google_maps_satellite && (
          <MapLink href={links.google_maps_satellite}>
            <Globe size={9} /> Google Maps
          </MapLink>
        )}
        {links?.google_earth && (
          <MapLink href={links.google_earth}>
            <Globe size={9} /> Google Earth
          </MapLink>
        )}
      </div>

      {(obs.before || obs.after) && (
        <p className="mt-1.5 font-mono text-[9px] text-faint">
          Sentinel-2 {[obs.before?.scene_id, obs.after?.scene_id].filter(Boolean).join(" → ")}
        </p>
      )}
    </div>
  );
}

export default function SatelliteVerification({ companyId }: { companyId: string }) {
  const { data, loading, error } = useApi(() => api.satellite(companyId), [companyId]);

  return (
    <div className="rounded-xl border border-hairline bg-surface shadow-panel">
      <div className="flex items-start gap-2 border-b border-hairline px-4 py-3">
        <Satellite size={14} className="mt-0.5 shrink-0 text-faint" />
        <div>
          <h3 className="text-sm font-semibold text-txt">Ground truth</h3>
          <p className="text-[11px] text-faint">
            Physical assets located in an open registry, then checked against dated
            satellite imagery. Seeing construction can raise a claim to VERIFIED; not
            seeing it never lowers a score.
          </p>
        </div>
      </div>

      <div className="p-4">
        {loading && (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {[0, 1].map((i) => (
              <div
                key={i}
                className="h-56 animate-pulse rounded-lg border border-hairline bg-raised/30"
              />
            ))}
          </div>
        )}

        {error && (
          <p className="text-[11px] text-faint">
            Could not reach the imagery services. This panel is best-effort and never
            affects the score on its own.
          </p>
        )}

        {data && data.observations.length === 0 && data.located === 0 && (
          <p className="text-[11.5px] leading-snug text-faint">
            No physical assets on file for {data.company}. Satellite checks apply to
            claims about plants, farms and land — not to disclosure, governance or
            workforce claims, which is most of a sustainability report.
          </p>
        )}

        {data && data.observations.length === 0 && data.located > 0 && (
          <p className="text-[11.5px] leading-snug text-faint">
            {data.located} asset{data.located === 1 ? "" : "s"} located for {data.company},
            but no imagery has been fetched for {data.before_year}–{data.after_year} yet.
            Imagery is precomputed in batch, not on page load —{" "}
            <code className="rounded bg-raised/60 px-1 py-0.5 font-mono text-[10px]">
              python -m backend.data.satverify {data.company_id}
            </code>
          </p>
        )}

        {data && data.observations.length > 0 && (
          <>
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              {data.observations.map((obs) => (
                <SiteCard key={obs.site.site_id} obs={obs} />
              ))}
            </div>
            <p className="mt-3 border-t border-hairline pt-2 text-[10px] leading-snug text-faint">
              {data.disclosure}
            </p>
          </>
        )}
      </div>
    </div>
  );
}
