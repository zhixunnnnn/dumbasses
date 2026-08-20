// When the frontend is hosted separately (e.g. Vercel), point it at the API with
// VITE_API_BASE_URL. Empty default keeps same-origin paths for the Railway build,
// where FastAPI serves both the API and this bundle.
const RAW = import.meta.env.VITE_API_BASE_URL ?? "";

export const API_BASE = RAW.replace(/\/+$/, "");

export const apiUrl = (path: string): string => `${API_BASE}${path}`;
