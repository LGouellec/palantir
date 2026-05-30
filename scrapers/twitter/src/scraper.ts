import fs from "node:fs";
import path from "node:path";
import { Scraper, type Tweet } from "@the-convocation/twitter-scraper";
import type { AppConfig } from "./config.js";
import { log } from "./logger.js";

/** Normalized, flattened tweet shape we publish downstream. */
export interface TweetRecord {
  id: string;
  conversationId?: string;
  userId?: string;
  username?: string;
  name?: string;
  text?: string;
  html?: string;
  permanentUrl?: string;
  timestamp?: number; // epoch seconds (from the library)
  timeIso?: string;
  likes?: number;
  retweets?: number;
  replies?: number;
  views?: number;
  bookmarkCount?: number;
  hashtags: string[];
  mentions: string[];
  urls: string[];
  photos: string[];
  videos: string[];
  isRetweet?: boolean;
  isReply?: boolean;
  isQuoted?: boolean;
  // Provenance: which query/user surfaced this tweet
  source: string;
  scrapedAt: string;
  // All of the above, rendered as a single markdown document. Downstream
  // sentiment analysis reads `$.content_md` (see
  // analysis/flink/statements/market_sentiment_analysis.sql), matching the
  // WSJ / seeking-alpha scrapers.
  content_md: string;
}

/**
 * Render a tweet record as a single markdown document grouping every field:
 * a heading, a metadata block of `**Key:** value` lines (empty ones omitted),
 * then the tweet text below a `---` separator.
 */
export function toMarkdown(r: Omit<TweetRecord, "content_md">): string {
  const author = r.name ? `${r.name} (@${r.username ?? "?"})` : `@${r.username ?? "?"}`;
  const lines: string[] = [`# Tweet by ${author}`, ""];

  const meta: [string, string | undefined][] = [
    ["ID", r.id || undefined],
    ["URL", r.permanentUrl],
    ["Posted", r.timeIso],
    ["Author ID", r.userId],
    ["Conversation ID", r.conversationId],
    ["Source", r.source],
    ["Scraped", r.scrapedAt],
  ];

  const engagement = [
    r.likes != null ? `👍 ${r.likes}` : null,
    r.retweets != null ? `🔁 ${r.retweets}` : null,
    r.replies != null ? `💬 ${r.replies}` : null,
    r.views != null ? `👁 ${r.views}` : null,
    r.bookmarkCount != null ? `🔖 ${r.bookmarkCount}` : null,
  ].filter(Boolean);
  if (engagement.length) meta.push(["Engagement", engagement.join(" · ")]);

  const flags = [
    r.isRetweet ? "retweet" : null,
    r.isReply ? "reply" : null,
    r.isQuoted ? "quote" : null,
  ].filter(Boolean);
  meta.push(["Type", flags.length ? flags.join(", ") : "original"]);

  if (r.hashtags.length) meta.push(["Hashtags", r.hashtags.map((h) => `#${h}`).join(" ")]);
  if (r.mentions.length) meta.push(["Mentions", r.mentions.map((m) => `@${m}`).join(" ")]);
  if (r.urls.length) meta.push(["Links", r.urls.join(", ")]);
  const mediaParts = [
    r.photos.length ? `${r.photos.length} photo(s)` : null,
    r.videos.length ? `${r.videos.length} video(s)` : null,
  ].filter(Boolean);
  if (mediaParts.length) meta.push(["Media", mediaParts.join(", ")]);

  for (const [key, value] of meta) {
    if (value) lines.push(`**${key}:** ${value}`);
  }

  lines.push("", "---", "", r.text ?? "");
  return lines.join("\n");
}

export function toRecord(tweet: Tweet, source: string): TweetRecord {
  const base: Omit<TweetRecord, "content_md"> = {
    id: tweet.id ?? "",
    conversationId: tweet.conversationId,
    userId: tweet.userId,
    username: tweet.username,
    name: tweet.name,
    text: tweet.text,
    html: tweet.html,
    permanentUrl: tweet.permanentUrl,
    timestamp: tweet.timestamp,
    timeIso: tweet.timeParsed
      ? new Date(tweet.timeParsed).toISOString()
      : tweet.timestamp
        ? new Date(tweet.timestamp * 1000).toISOString()
        : undefined,
    likes: tweet.likes,
    retweets: tweet.retweets,
    replies: tweet.replies,
    views: tweet.views,
    bookmarkCount: tweet.bookmarkCount,
    hashtags: tweet.hashtags ?? [],
    mentions: (tweet.mentions ?? [])
      .map((m) => m.username ?? "")
      .filter(Boolean),
    urls: tweet.urls ?? [],
    photos: (tweet.photos ?? []).map((p) => p.url).filter(Boolean),
    videos: (tweet.videos ?? []).map((v) => v.url ?? "").filter(Boolean),
    isRetweet: tweet.isRetweet,
    isReply: tweet.isReply,
    isQuoted: tweet.isQuoted,
    source,
    scrapedAt: new Date().toISOString(),
  };
  return { ...base, content_md: toMarkdown(base) };
}

export class TwitterClient {
  private scraper = new Scraper();

  constructor(private readonly cfg: AppConfig) {}

  /**
   * Authenticate. Cookies are strongly preferred over username/password
   * login — the library warns that any account logged in via credentials may
   * be banned. If a cookies file is configured and present we use it; on a
   * successful credential login we persist fresh cookies back to that file.
   */
  async authenticate(): Promise<void> {
    // 1. Cookies from a JSON file (browser-extension export, tough-cookie
    //    JSON, an array of strings, or a raw "a=b; c=d" string).
    if (this.cfg.cookiesFile && fs.existsSync(this.cfg.cookiesFile)) {
      const raw = fs.readFileSync(path.resolve(this.cfg.cookiesFile), "utf8");
      const cookies = this.toTwitterCookies(this.parseCookieFile(raw));
      if (cookies.length > 0) {
        await this.scraper.setCookies(cookies);
        if (await this.scraper.isLoggedIn()) {
          log.ok(`Authenticated via cookies file (${cookies.length} cookies)`);
          return;
        }
        log.warn(
          "Cookies file did not yield a logged-in session — " +
            "auth_token/ct0 may be expired, or exported from the wrong account",
        );
      }
    }

    // 2. Cookie string from env (e.g. exported from a browser)
    if (this.cfg.cookieString) {
      const cookies = this.toTwitterCookies(
        this.parseCookiePairs(this.cfg.cookieString),
      );
      await this.scraper.setCookies(cookies);
      if (await this.scraper.isLoggedIn()) {
        log.ok("Authenticated via TWITTER_COOKIES");
        return;
      }
      log.warn("TWITTER_COOKIES did not yield a logged-in session");
    }

    // 3. Credential login (last resort)
    if (this.cfg.username && this.cfg.password) {
      log.warn(
        "Logging in with username/password — this account risks being banned",
      );
      await this.scraper.login(
        this.cfg.username,
        this.cfg.password,
        this.cfg.email,
      );
      if (await this.scraper.isLoggedIn()) {
        log.ok("Authenticated via credentials");
        await this.persistCookies();
        return;
      }
      throw new Error("Credential login failed");
    }

    log.warn(
      "No credentials provided — continuing unauthenticated (limited / may fail)",
    );
  }

  /** Cookies that must be present for an authenticated session. */
  private static readonly ESSENTIAL_COOKIES = ["auth_token", "ct0"];

  /**
   * Domain the library scopes its cookie jar to. Since v0.16 the scraper hits
   * x.com (`twUrl = "https://x.com"`); tough-cookie drops any cookie whose
   * `Domain` doesn't match the jar URL, so this MUST track the library's host.
   */
  private static readonly COOKIE_DOMAIN = ".x.com";

  /**
   * Render name/value pairs as Set-Cookie strings scoped to the library's
   * host (see COOKIE_DOMAIN).
   *
   * Forcing the domain here means cookies are accepted regardless of where
   * they were exported from, and also sidesteps browser-extension exports that
   * use `name` instead of the tough-cookie `key` field. Warns when the
   * essential cookies are missing.
   */
  private toTwitterCookies(pairs: { name: string; value: string }[]): string[] {
    const seen = new Set(pairs.map((p) => p.name));
    const missing = TwitterClient.ESSENTIAL_COOKIES.filter((n) => !seen.has(n));
    if (missing.length > 0) {
      log.warn(
        `Cookies missing essential ${missing.join(", ")} — login will likely ` +
          "fail. Export auth_token AND ct0 from a logged-in x.com session.",
      );
    } else {
      log.debug(`Loaded cookies: ${[...seen].join(", ")}`);
    }
    return pairs
      .filter((p) => p.name && p.value)
      .map(
        (p) =>
          `${p.name}=${p.value}; Domain=${TwitterClient.COOKIE_DOMAIN}; Path=/`,
      );
  }

  /**
   * Parse a cookies file in any common shape into name/value pairs:
   * a JSON array of browser-extension objects (`{name,value}`), tough-cookie
   * objects (`{key,value}`), plain "name=value" strings, or a raw cookie
   * string (`a=b; c=d`).
   */
  private parseCookieFile(raw: string): { name: string; value: string }[] {
    const trimmed = raw.trim();
    try {
      const parsed = JSON.parse(trimmed);
      if (Array.isArray(parsed)) {
        return parsed
          .map((c) => this.toCookiePair(c))
          .filter((p): p is { name: string; value: string } => p !== null);
      }
    } catch {
      // Not JSON — treat the whole file as a raw cookie string.
    }
    return this.parseCookiePairs(trimmed);
  }

  /** One cookie entry (object or string) → name/value, or null if unusable. */
  private toCookiePair(c: unknown): { name: string; value: string } | null {
    if (typeof c === "string") {
      const [pair] = this.parseCookiePairs(c);
      return pair ?? null;
    }
    if (c && typeof c === "object") {
      const o = c as Record<string, unknown>;
      const name = (o.name ?? o.key) as string | undefined; // extension | tough-cookie
      const value = o.value;
      if (name && value != null) return { name, value: String(value) };
    }
    return null;
  }

  /** Split a raw cookie string ("a=b; c=d") into name/value pairs. */
  private parseCookiePairs(raw: string): { name: string; value: string }[] {
    return raw
      .split(";")
      .map((c) => c.trim())
      .filter(Boolean)
      .map((c) => {
        const idx = c.indexOf("=");
        return idx > 0
          ? { name: c.slice(0, idx).trim(), value: c.slice(idx + 1).trim() }
          : null;
      })
      .filter((p): p is { name: string; value: string } => p !== null);
  }

  /** Persist the current session cookies so the next run can skip login. */
  async persistCookies(): Promise<void> {
    if (!this.cfg.cookiesFile) return;
    try {
      const cookies = await this.scraper.getCookies();
      const resolved = path.resolve(this.cfg.cookiesFile);
      fs.mkdirSync(path.dirname(resolved), { recursive: true });
      fs.writeFileSync(resolved, JSON.stringify(cookies), "utf8");
      log.ok(`Persisted ${cookies.length} cookies to ${resolved}`);
    } catch (err) {
      log.warn(`Could not persist cookies: ${String(err)}`);
    }
  }

  /** Tweets matching a search query. */
  searchTweets(query: string): AsyncGenerator<Tweet, void> {
    return this.scraper.searchTweets(
      query,
      this.cfg.maxTweets,
      this.cfg.searchMode,
    );
  }

  /** Tweets from a user's timeline. */
  getTweets(username: string): AsyncGenerator<Tweet, void> {
    return this.scraper.getTweets(username, this.cfg.maxTweets);
  }

  /** Whether the current session is still authenticated. */
  isLoggedIn(): Promise<boolean> {
    return this.scraper.isLoggedIn();
  }

  /**
   * Whether any auth method is configured. When nothing is set the scraper
   * runs unauthenticated by design, so there is nothing to refresh.
   */
  isAuthConfigured(): boolean {
    return Boolean(
      this.cfg.cookiesFile ||
        this.cfg.cookieString ||
        (this.cfg.username && this.cfg.password),
    );
  }
}
