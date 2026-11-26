package io.palantir.stream.newsmerger;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonPropertyOrder;

/**
 * Output record written to the {@code financial-news} topic.
 * Shape follows analysis/stream/message-output.md.
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
@JsonPropertyOrder({"id", "author", "category", "content", "content_md", "published_date", "scraped_at", "title", "url", "source"})
public record FinancialNews(
        @JsonProperty("id") String id,
        @JsonProperty("author") String author,
        @JsonProperty("category") String category,
        @JsonProperty("content") String content,
        @JsonProperty("content_md") String contentMd,
        @JsonProperty("published_date") String publishedDate,
        @JsonProperty("scraped_at") String scrapedAt,
        @JsonProperty("title") String title,
        @JsonProperty("url") String url,
        @JsonProperty("source") String source) {
}
