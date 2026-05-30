/**
 * Tiny leveled logger. VERBOSE=true enables debug output.
 */
const verbose = process.env.VERBOSE === "true";

function ts(): string {
  return new Date().toISOString();
}

export const log = {
  info: (...args: unknown[]) => console.log(`[${ts()}] ℹ️ `, ...args),
  warn: (...args: unknown[]) => console.warn(`[${ts()}] ⚠️ `, ...args),
  error: (...args: unknown[]) => console.error(`[${ts()}] ❌`, ...args),
  ok: (...args: unknown[]) => console.log(`[${ts()}] ✅`, ...args),
  debug: (...args: unknown[]) => {
    if (verbose) console.log(`[${ts()}] 🐛`, ...args);
  },
};
