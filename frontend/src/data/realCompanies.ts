export type RawCompany = {
  /** Engine company_id. Explicit because it can no longer be derived from the ticker:
   *  "U96.SI" reduces to "U96" and happened to match, but "5347.KL" reduces to "5347"
   *  while the engine id is "TNB". Deriving it silently broke every non-SGX row. */
  id: string;
  n: string;
  t: string;
  s: string;
  r: string;
  hq: string;
  web: string;
  /** Founding year, or null when we have no sourced value. Never guessed. */
  est: number | null;
  /** Full-time headcount, or null when the source does not publish one. */
  emp: number | null;
  /** Market cap in BILLIONS OF USD. Local-currency caps from Yahoo converted at live
   *  Yahoo FX (SGDUSD=X etc.), because the UI labels this figure "$" and sums it across
   *  the panel — mixing SGD, MYR, THB, IDR and VND would make both meaningless. */
  cap: number;
  bio: string;
};

// Identity and public profile only for the ten ASEAN utilities the engine covers:
// name, ticker, sector, region, HQ, website, founding year, headcount and market cap.
// This table carries no scores of any kind -- every ESG, evidence and momentum figure
// comes from the API.
//
// cap and emp were read from Yahoo Finance on 2026-08-24 and cross-checked against
// MarketScreener (Sembcorp: 8.37 computed here vs 8.47 "Capi.($)" reported there).
// Headcount is published for only five of the ten, and no founding year could be
// sourced for any of them, so those fields are null rather than filled in.
export const RAW_COMPANIES: RawCompany[] = [
  { id: "U96", n: "Sembcorp Industries", t: "U96.SI", s: "Utilities", r: "Southeast Asia", hq: "Singapore", web: "sembcorp.com", est: null, emp: 4629, cap: 8.37, bio: "Utilities and urban development; renewables-led energy transition." },
  { id: "TNB", n: "Tenaga Nasional", t: "5347.KL", s: "Utilities", r: "Southeast Asia", hq: "Kuala Lumpur", web: "tnb.com.my", est: null, emp: 31063, cap: 20.56, bio: "Malaysia's national electricity utility: generation, transmission and distribution." },
  { id: "YTLP", n: "YTL Power International", t: "6742.KL", s: "Utilities", r: "Southeast Asia", hq: "Kuala Lumpur", web: "ytlpowerinternational.com", est: null, emp: null, cap: 11.48, bio: "Multi-utility: power generation, water and sewerage, telecoms and data centres." },
  { id: "EGCO", n: "Electricity Generating", t: "EGCO.BK", s: "Utilities", r: "Southeast Asia", hq: "Bangkok", web: "egco.com", est: null, emp: null, cap: 2.11, bio: "Thailand's first independent power producer; thermal and renewable generation across Asia-Pacific." },
  { id: "RATCH", n: "Ratch Group", t: "RATCH.BK", s: "Utilities", r: "Southeast Asia", hq: "Nonthaburi", web: "ratch.co.th", est: null, emp: null, cap: 2.45, bio: "Thai power producer with domestic and overseas generation plus infrastructure assets." },
  { id: "BGRIM", n: "B.Grimm Power", t: "BGRIM.BK", s: "Utilities", r: "Southeast Asia", hq: "Bangkok", web: "bgrimmpower.com", est: null, emp: null, cap: 1.49, bio: "Thai independent power producer; industrial cogeneration and solar." },
  { id: "GULF", n: "Gulf Development", t: "GULF.BK", s: "Utilities", r: "Southeast Asia", hq: "Bangkok", web: "gulf.co.th", est: null, emp: null, cap: 29.06, bio: "Thai power and infrastructure group; gas-fired and renewable generation." },
  { id: "PGAS", n: "Perusahaan Gas Negara", t: "PGAS.JK", s: "Utilities", r: "Southeast Asia", hq: "Jakarta", web: "pgn.co.id", est: null, emp: 3319, cap: 2.08, bio: "Indonesia's state-linked natural gas transmission and distribution utility." },
  { id: "POWR", n: "Cikarang Listrindo", t: "POWR.JK", s: "Utilities", r: "Southeast Asia", hq: "Jakarta", web: "listrindo.com", est: null, emp: 849, cap: 0.82, bio: "Private power producer supplying industrial estates east of Jakarta." },
  { id: "POW", n: "PetroVietnam Power", t: "POW.VN", s: "Utilities", r: "Southeast Asia", hq: "Hanoi", web: "pvpower.vn", est: null, emp: 2182, cap: 1.6, bio: "Vietnam's second-largest power producer; gas, coal and hydro generation." },
];
