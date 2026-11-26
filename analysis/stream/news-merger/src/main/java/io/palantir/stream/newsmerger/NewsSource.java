package io.palantir.stream.newsmerger;

import com.fasterxml.jackson.databind.JsonNode;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * One enum constant per input topic, each knowing how to map its own JSON layout
 * (see analysis/stream/messages-input.md) onto {@link FinancialNews}.
 *
 * Id derivation mirrors analysis/flink/statements/news_sentiment.sql so the same
 * article gets the same id in both pipelines.
 */
public enum NewsSource {

    INVESTING("investing", "investing-news") {
        @Override
        FinancialNews map(JsonNode n) {
            return new FinancialNews(
                    firstNonBlank(text(n, "id"), text(n, "url")),
                    text(n, "author"),
                    text(n, "category"),
                    text(n, "content"),
                    text(n, "content_md"),
                    DateNormalizer.normalize(text(n, "published_date")),
                    DateNormalizer.normalize(text(n, "scraped_at")),
                    text(n, "title"),
                    text(n, "url"),
                    sourceId());
        }
    },

    SEEKING_ALPHA("seeking-alpha", "seeking-alpha-news") {
        private final Pattern idPattern = Pattern.compile("/news/([0-9]+)");

        @Override
        FinancialNews map(JsonNode n) {
            String url = text(n, "url");
            return new FinancialNews(
                    firstNonBlank(extract(idPattern, url), url),
                    text(n, "author"),
                    text(n, "category"),
                    text(n, "content"),
                    text(n, "content_md"),
                    DateNormalizer.normalize(text(n, "published_date")),
                    DateNormalizer.normalize(text(n, "scraped_at")),
                    text(n, "title"),
                    url,
                    sourceId());
        }
    },

    WSJ("wsj", "wsj-articles") {
        private final Pattern idPattern = Pattern.compile("-([0-9a-f]{8})(?:[/?]|$)");
        private final Pattern categoryPattern = Pattern.compile("https://www\\.wsj\\.com/([^/?#]+)");

        @Override
        FinancialNews map(JsonNode n) {
            String url = text(n, "url");
            return new FinancialNews(
                    firstNonBlank(extract(idPattern, url), url),
                    text(n, "author"),
                    extract(categoryPattern, url),
                    text(n, "content"),
                    text(n, "content_md"),
                    DateNormalizer.normalize(text(n, "published_date")),
                    DateNormalizer.normalize(text(n, "scraped_at")),
                    text(n, "title"),
                    url,
                    sourceId());
        }
    },

    TWITTER("twitter", "twitter-tweets") {
        @Override
        FinancialNews map(JsonNode n) {
            String published = text(n, "timeIso");
            if (published == null && n.hasNonNull("timestamp")) {
                published = DateNormalizer.fromEpochSeconds(n.get("timestamp").asLong());
            }
            return new FinancialNews(
                    firstNonBlank(text(n, "id"), text(n, "permanentUrl")),
                    firstNonBlank(text(n, "username"), text(n, "name")),
                    // the search query / timeline the tweet was scraped from
                    text(n, "source"),
                    text(n, "text"),
                    text(n, "content_md"),
                    DateNormalizer.normalize(published),
                    DateNormalizer.normalize(text(n, "scrapedAt")),
                    // tweets have no title (same as the Flink pipeline)
                    "",
                    text(n, "permanentUrl"),
                    sourceId());
        }
    };

    private final String sourceId;
    private final String defaultTopic;

    NewsSource(String sourceId, String defaultTopic) {
        this.sourceId = sourceId;
        this.defaultTopic = defaultTopic;
    }

    /** Value written to the {@code source} field of the output record, e.g. {@code seeking-alpha}. */
    public String sourceId() {
        return sourceId;
    }

    public String defaultTopic() {
        return defaultTopic;
    }

    /** Env var used to override this source's input topic, e.g. {@code INPUT_TOPIC_WSJ}. */
    public String topicEnvVar() {
        return "INPUT_TOPIC_" + name();
    }

    abstract FinancialNews map(JsonNode node);

    static String text(JsonNode node, String field) {
        JsonNode value = node.get(field);
        if (value == null || value.isNull() || value.isMissingNode()) {
            return null;
        }
        return value.isValueNode() ? value.asText() : value.toString();
    }

    static String extract(Pattern pattern, String input) {
        if (input == null) {
            return null;
        }
        Matcher m = pattern.matcher(input);
        return m.find() ? m.group(1) : null;
    }

    static String firstNonBlank(String... values) {
        for (String v : values) {
            if (v != null && !v.isBlank()) {
                return v;
            }
        }
        return null;
    }
}
