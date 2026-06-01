import fs from "node:fs";
import path from "node:path";
import { SearchMode } from "@the-convocation/twitter-scraper";
import { log } from "./logger.js";

/**
 * Runtime configuration, loaded from environment variables.
 *
 * Mirrors the env-driven pattern used by the other scrapers in this repo
 * (see ../seeking-alpha/entrypoint.sh) so it slots into the same
 * docker-compose / Kafka wiring.
 */
export interface AppConfig {
  // What to scrape
  queries: string[];
  users: string[];
  searchMode: SearchMode;
  maxTweets: number;
  delayMs: number;
  // Only emit tweets at/after this point: "today", a "YYYY-MM-DD" date, or
  // undefined for no lower bound.
  since?: string;

  // Run mode
  continuous: boolean;
  continuousIntervalSec: number;

  // Authentication (cookies preferred over login)
  cookieString?: string;
  cookiesFile?: string;
  username?: string;
  password?: string;
  email?: string;

  // Kafka
  kafkaEnabled: boolean;
  kafkaTopic: string;
  kafkaBootstrapServers?: string;
  kafkaConfigFile?: string;

  // History / dedup
  historyFile: string;
  historyTtlDays: number;

  // Local output
  saveLocal: boolean;
  outputDir: string;
}

function envStr(name: string, fallback?: string): string | undefined {
  const v = process.env[name];
  return v === undefined || v === "" ? fallback : v;
}

function envBool(name: string, fallback = false): boolean {
  const v = process.env[name];
  if (v === undefined || v === "") return fallback;
  return ["1", "true", "yes", "on"].includes(v.toLowerCase());
}

function envInt(name: string, fallback: number): number {
  const v = process.env[name];
  if (v === undefined || v === "") return fallback;
  const n = Number.parseInt(v, 10);
  return Number.isNaN(n) ? fallback : n;
}

function envList(name: string): string[] {
  const v = process.env[name];
  if (!v) return [];
  return v
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function parseSearchMode(raw: string | undefined): SearchMode {
  switch ((raw ?? "Latest").toLowerCase()) {
    case "top":
      return SearchMode.Top;
    case "latest":
      return SearchMode.Latest;
    case "photos":
      return SearchMode.Photos;
    case "videos":
      return SearchMode.Videos;
    case "users":
      return SearchMode.Users;
    default:
      log.warn(`Unknown SEARCH_MODE "${raw}", defaulting to Latest`);
      return SearchMode.Latest;
  }
}

/**
 * Resolve the configured `SINCE` into a UTC cutoff Date, or null when no
 * lower bound is set. `"today"` is the start of the current UTC day (recomputed
 * on each call, so a long-running continuous scraper rolls forward day to day).
 */
export function resolveSinceCutoff(since: string | undefined): Date | null {
  if (!since) return null;
  if (since.toLowerCase() === "today") {
    const now = new Date();
    return new Date(
      Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()),
    );
  }
  const d = new Date(`${since}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) {
    log.warn(`Invalid SINCE "${since}" — ignoring date filter`);
    return null;
  }
  return d;
}

/** Format a Date as `YYYY-MM-DD` (UTC) for Twitter's `since:` search operator. */
export function toSearchDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function loadConfig(): AppConfig {
  const cfg: AppConfig = {
    queries: envList("TWITTER_QUERIES"),
    users: envList("TWITTER_USERS"),
    searchMode: parseSearchMode(envStr("SEARCH_MODE")),
    maxTweets: envInt("MAX_TWEETS", 50),
    delayMs: envInt("DELAY_MS", 1500),
    since: envStr("SINCE"),

    continuous: envBool("CONTINUOUS", false),
    continuousIntervalSec: envInt("CONTINUOUS_INTERVAL", 300),

    cookieString: envStr("TWITTER_COOKIES"),
    cookiesFile: envStr("TWITTER_COOKIES_FILE"),
    username: envStr("TWITTER_USERNAME"),
    password: envStr("TWITTER_PASSWORD"),
    email: envStr("TWITTER_EMAIL"),

    kafkaEnabled: envBool("KAFKA_ENABLED", false),
    kafkaTopic: envStr("KAFKA_TOPIC", "twitter-tweets")!,
    kafkaBootstrapServers: envStr("KAFKA_BOOTSTRAP_SERVERS"),
    kafkaConfigFile: envStr("KAFKA_CONFIG_FILE"),

    historyFile: envStr("HISTORY_FILE", "history/scraped_history.json")!,
    historyTtlDays: envInt("HISTORY_TTL_DAYS", 30),

    saveLocal: envBool("SAVE_LOCAL", false),
    outputDir: envStr("OUTPUT_DIR", "output")!,
  };

  if (cfg.queries.length === 0 && cfg.users.length === 0) {
    throw new Error(
      "Nothing to scrape: set TWITTER_QUERIES and/or TWITTER_USERS",
    );
  }

  return cfg;
}

/**
 * Parse a Confluent-style `kafka_config.properties` file (key=value lines,
 * `#` comments) into a flat map. Same format the Python scrapers use.
 */
export function parseKafkaProperties(file: string): Record<string, string> {
  const resolved = path.resolve(file);
  if (!fs.existsSync(resolved)) {
    log.warn(`Kafka config file not found: ${resolved}`);
    return {};
  }
  const out: Record<string, string> = {};
  for (const rawLine of fs.readFileSync(resolved, "utf8").split("\n")) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const idx = line.indexOf("=");
    if (idx === -1) continue;
    out[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
  }
  log.ok(`Loaded Kafka config from ${resolved}`);
  return out;
}
