// The deployment workflow supplies VITE_DEEPSEEK_API_KEY from a GitHub Actions secret.
// Vite replaces this value at build time so the browser can call DeepSeek directly.
export const DEEPSEEK_API_KEY = import.meta.env.VITE_DEEPSEEK_API_KEY ?? '';
