export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8000";

export const apiUrl = (path: string) => `${API_BASE}${path}`;
