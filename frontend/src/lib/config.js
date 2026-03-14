/**
 * Returns the backend API base URL.
 * Falls back to '' (relative URL through ingress) when env var is missing.
 */
export const API_BASE = process.env.REACT_APP_BACKEND_URL || '';
