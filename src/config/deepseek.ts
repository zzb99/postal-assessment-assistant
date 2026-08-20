/**
 * GitHub Pages 构建时由工作流注入 VITE_DEEPSEEK_API_KEY。
 * 本机可通过 Vite 环境变量覆盖；不要在这里填写或提交真实密钥。
 */
export const DEEPSEEK_API_KEY = import.meta.env.VITE_DEEPSEEK_API_KEY ?? '';
