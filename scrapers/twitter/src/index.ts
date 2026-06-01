import fs from "node:fs";
import path from "node:path";
import "dotenv/config";
import type { Tweet } from "@the-convocation/twitter-scraper";
import {
  loadConfig,
  resolveSinceCutoff,
  toSearchDate,
  type AppConfig,
} from "./config.js";
import { History } from "./history.js";
import { KafkaSink } from "./kafka.js";
import { log } from "./logger.js";
import { TwitterClient, toRecord, type TweetRecord } from "./scraper.js";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Epoch ms of a tweet, from the parsed time or the raw timestamp. */
function tweetTimeMs(tweet: Tweet): number | null {
  if (tweet.timeParsed) return new Date(tweet.timeParsed).getTime();
  if (tweet.timestamp) return tweet.timestamp * 1000;
  return null;
}

/** Consume one tweet source (search query or user timeline), emitting records. */
async function drain(
  gen: AsyncGenerator<Tweet, void>,
  source: string,
  cfg: AppConfig,
  history: History,
  sink: KafkaSink | null,
  localBuf: TweetRecord[],
  cutoffMs: number | null,
): Promise<number> {
  let emitted = 0;
  try {
    for await (const tweet of gen) {
      if (!tweet.id) continue;
      // Date lower bound (e.g. SINCE=today). Timelines have no `since:`
      // operator, so they're filtered here; skip rather than break since
      // pinned/out-of-order tweets can appear among newer ones.
      if (cutoffMs !== null) {
        const ts = tweetTimeMs(tweet);
        if (ts !== null && ts < cutoffMs) {
          log.debug(`skip pre-cutoff ${tweet.id}`);
          continue;
        }
      }
      if (history.has(tweet.id)) {
        log.debug(`skip duplicate ${tweet.id}`);
        continue;
      }
      const record = toRecord(tweet, source);
      if (sink) await sink.send(record.username ?? source, record);
      if (cfg.saveLocal) localBuf.push(record);
      history.add(tweet.id);
      emitted++;
    }
  } catch (err) {
    log.error(`Error draining "${source}": ${String(err)}`);
  }
  return emitted;
}

function writeLocal(cfg: AppConfig, records: TweetRecord[]): void {
  if (records.length === 0) return;
  fs.mkdirSync(path.resolve(cfg.outputDir), { recursive: true });
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const file = path.resolve(cfg.outputDir, `tweets-${stamp}.jsonl`);
  fs.writeFileSync(
    file,
    records.map((r) => JSON.stringify(r)).join("\n") + "\n",
    "utf8",
  );
  log.ok(`Wrote ${records.length} tweets to ${file}`);
}

/**
 * Refresh the session if it has dropped (cookies expired mid-run, etc.).
 * Re-runs the full auth chain, which re-reads the cookies file / cookie string
 * and falls back to credential login — persisting fresh cookies on success.
 */
async function ensureAuthenticated(
  cfg: AppConfig,
  client: TwitterClient,
): Promise<void> {
  if (!client.isAuthConfigured()) return; // running unauthenticated by choice
  if (await client.isLoggedIn()) return;
  log.warn("Session no longer logged in — re-authenticating…");
  try {
    await client.authenticate();
  } catch (err) {
    log.error(`Re-authentication failed: ${String(err)}`);
  }
}

async function runCycle(
  cfg: AppConfig,
  client: TwitterClient,
  history: History,
  sink: KafkaSink | null,
): Promise<void> {
  await ensureAuthenticated(cfg, client);

  const localBuf: TweetRecord[] = [];
  let total = 0;

  // Date lower bound (recomputed each cycle so SINCE=today rolls forward).
  const cutoff = resolveSinceCutoff(cfg.since);
  const cutoffMs = cutoff ? cutoff.getTime() : null;
  const sinceOp = cutoff ? ` since:${toSearchDate(cutoff)}` : "";

  for (const query of cfg.queries) {
    // Append the server-side `since:` operator unless the query already has one.
    const q = sinceOp && !/\bsince:/i.test(query) ? `${query}${sinceOp}` : query;
    log.info(`Searching: "${q}" (mode=${cfg.searchMode}, max=${cfg.maxTweets})`);
    total += await drain(
      client.searchTweets(q),
      `search:${query}`,
      cfg,
      history,
      sink,
      localBuf,
      cutoffMs,
    );
    await sleep(cfg.delayMs);
  }

  for (const user of cfg.users) {
    log.info(`Fetching timeline: @${user} (max=${cfg.maxTweets})`);
    total += await drain(
      client.getTweets(user),
      `user:${user}`,
      cfg,
      history,
      sink,
      localBuf,
      cutoffMs,
    );
    await sleep(cfg.delayMs);
  }

  history.save();
  if (cfg.saveLocal) writeLocal(cfg, localBuf);
  log.ok(`Cycle complete: ${total} new tweets`);
}

async function main(): Promise<void> {
  const cfg = loadConfig();
  log.info(
    `Config: queries=${cfg.queries.length} users=${cfg.users.length} ` +
      `kafka=${cfg.kafkaEnabled} continuous=${cfg.continuous} ` +
      `since=${cfg.since ?? "<none>"}`,
  );

  const history = new History(cfg.historyFile, cfg.historyTtlDays);
  const client = new TwitterClient(cfg);
  await client.authenticate();

  let sink: KafkaSink | null = null;
  if (cfg.kafkaEnabled) {
    sink = new KafkaSink(cfg);
    await sink.connect();
  } else {
    log.warn("KAFKA_ENABLED=false — tweets will not be published to Kafka");
  }

  let stopping = false;
  const shutdown = async (signal: string) => {
    if (stopping) return;
    stopping = true;
    log.info(`Received ${signal}, shutting down…`);
    history.save();
    if (sink) await sink.disconnect();
    process.exit(0);
  };
  process.on("SIGINT", () => void shutdown("SIGINT"));
  process.on("SIGTERM", () => void shutdown("SIGTERM"));

  if (!cfg.continuous) {
    await runCycle(cfg, client, history, sink);
    if (sink) await sink.disconnect();
    return;
  }

  log.info(`Continuous mode: every ${cfg.continuousIntervalSec}s`);
  while (!stopping) {
    await runCycle(cfg, client, history, sink);
    log.info(`Sleeping ${cfg.continuousIntervalSec}s…`);
    await sleep(cfg.continuousIntervalSec * 1000);
  }
}

main().catch((err) => {
  log.error(err instanceof Error ? err.stack ?? err.message : String(err));
  process.exit(1);
});
