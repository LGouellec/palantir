import fs from "node:fs";
import path from "node:path";
import { log } from "./logger.js";

interface HistoryEntry {
  seenAt: number; // epoch ms
}

/**
 * File-backed dedup store of tweet IDs with TTL pruning, so continuous runs
 * don't re-emit the same tweet. Mirrors the history-file approach used by the
 * other scrapers in this repo.
 */
export class History {
  private entries = new Map<string, HistoryEntry>();

  constructor(
    private readonly file: string,
    private readonly ttlDays: number,
  ) {
    this.load();
  }

  private load(): void {
    const resolved = path.resolve(this.file);
    if (!fs.existsSync(resolved)) {
      log.debug(`No history file at ${resolved}, starting fresh`);
      return;
    }
    try {
      const raw = JSON.parse(fs.readFileSync(resolved, "utf8")) as Record<
        string,
        HistoryEntry
      >;
      for (const [id, entry] of Object.entries(raw)) {
        this.entries.set(id, entry);
      }
      this.prune();
      log.info(`Loaded ${this.entries.size} ids from history`);
    } catch (err) {
      log.warn(`Failed to read history file, starting fresh: ${String(err)}`);
    }
  }

  private prune(): void {
    if (this.ttlDays <= 0) return;
    const cutoff = Date.now() - this.ttlDays * 86_400_000;
    for (const [id, entry] of this.entries) {
      if (entry.seenAt < cutoff) this.entries.delete(id);
    }
  }

  has(id: string): boolean {
    return this.entries.has(id);
  }

  add(id: string): void {
    this.entries.set(id, { seenAt: Date.now() });
  }

  save(): void {
    const resolved = path.resolve(this.file);
    fs.mkdirSync(path.dirname(resolved), { recursive: true });
    const obj: Record<string, HistoryEntry> = {};
    for (const [id, entry] of this.entries) obj[id] = entry;
    fs.writeFileSync(resolved, JSON.stringify(obj), "utf8");
    log.debug(`Saved ${this.entries.size} ids to ${resolved}`);
  }
}
