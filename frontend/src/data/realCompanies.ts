export type RawCompany = {
  n: string;
  t: string;
  s: string;
  r: string;
  hq: string;
  web: string;
  est: number;
  emp: number;
  cap: number;
  bio: string;
};

// Identity and public profile only for the ten SGX issuers the engine covers:
// name, ticker, sector, region, HQ, website, founding year, headcount and
// approximate market cap. This table carries no scores of any kind -- every
// ESG, evidence and momentum figure comes from the API.
export const RAW_COMPANIES: RawCompany[] = [
  { n: "Sembcorp Industries", t: "U96.SI", s: "Utilities", r: "Southeast Asia", hq: "Singapore", web: "sembcorp.com", est: 1998, emp: 7, cap: 11, bio: "Utilities and urban development; renewables-led energy transition." },
  { n: "Keppel Ltd", t: "BN4.SI", s: "Industrials", r: "Southeast Asia", hq: "Singapore", web: "keppel.com", est: 1968, emp: 9, cap: 13, bio: "Asset manager and operator across energy, infrastructure and real estate." },
  { n: "Wilmar International", t: "F34.SI", s: "Consumer Staples", r: "Southeast Asia", hq: "Singapore", web: "wilmar-international.com", est: 1991, emp: 100, cap: 19, bio: "Agribusiness: palm oil, oilseeds, sugar and consumer foods." },
  { n: "Singapore Airlines", t: "C6L.SI", s: "Industrials", r: "Southeast Asia", hq: "Singapore", web: "singaporeair.com", est: 1947, emp: 15, cap: 19, bio: "Full-service international airline group." },
  { n: "DBS Group", t: "D05.SI", s: "Financials", r: "Southeast Asia", hq: "Singapore", web: "dbs.com", est: 1968, emp: 41, cap: 125, bio: "Southeast Asia's largest bank by assets." },
  { n: "OCBC", t: "O39.SI", s: "Financials", r: "Southeast Asia", hq: "Singapore", web: "ocbc.com", est: 1932, emp: 33, cap: 74, bio: "Singapore-based banking and wealth management group." },
  { n: "UOB", t: "U11.SI", s: "Financials", r: "Southeast Asia", hq: "Singapore", web: "uobgroup.com", est: 1935, emp: 27, cap: 60, bio: "Regional bank across ASEAN consumer and wholesale banking." },
  { n: "CapitaLand Investment", t: "9CI.SI", s: "Real Estate", r: "Southeast Asia", hq: "Singapore", web: "capitaland.com", est: 2021, emp: 14, cap: 14, bio: "Global real asset manager and property investment platform." },
  { n: "City Developments", t: "C09.SI", s: "Real Estate", r: "Southeast Asia", hq: "Singapore", web: "cdl.com.sg", est: 1963, emp: 8, cap: 5, bio: "Property developer, owner and hospitality operator." },
  { n: "Singtel", t: "Z74.SI", s: "Telecoms", r: "Southeast Asia", hq: "Singapore", web: "singtel.com", est: 1879, emp: 23, cap: 40, bio: "Regional telecommunications and digital infrastructure group." },
];
