using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Palantir.FlinkProxy;

/// <summary>
/// Renders a CosmosDB company document into a compact Markdown briefing that
/// covers every field. Intended as LLM input, so it stays flat, labelled and
/// deterministic rather than pretty.
/// </summary>
public static class ReportBuilder
{
    public static string BuildMarkdown(JsonObject doc)
    {
        var sb = new StringBuilder();

        string name = Str(doc["name"]);
        string ticker = Str(doc["ticker"]);
        sb.Append("# ").Append(name).Append(" (").Append(ticker).AppendLine(")");
        sb.AppendLine();

        AppendIdentity(sb, doc);
        AppendQuote(sb, doc);
        AppendRange52w(sb, doc);
        AppendRatios(sb, doc["ratios"] as JsonObject);
        AppendSentiment(sb, doc["sentiment"] as JsonObject);
        AppendAnalystGuidance(sb, doc["analyst_guidance"] as JsonArray);
        AppendNews(sb, doc["news"] as JsonArray);

        return sb.ToString().TrimEnd() + "\n";
    }

    private static void AppendIdentity(StringBuilder sb, JsonObject doc)
    {
        sb.AppendLine("## Identity");
        Line(sb, "Ticker", Str(doc["ticker"]));
        Line(sb, "Name", Str(doc["name"]));
        Line(sb, "Recommendation", Str(doc["recommendation_key"]));
        Line(sb, "Shares outstanding", Str(doc["shares_outstanding"]));
        Line(sb, "Last updated", Epoch(doc["timestamp"]));
        sb.AppendLine();
    }

    private static void AppendQuote(StringBuilder sb, JsonObject doc)
    {
        sb.AppendLine("## Quote");
        Line(sb, "Current price", Str(doc["current_price"]));
        Line(sb, "Previous close", Str(doc["previous_close"]));
        Line(sb, "Open", Str(doc["open"]));
        Line(sb, "Day high", Str(doc["day_high"]));
        Line(sb, "Day low", Str(doc["day_low"]));
        Line(sb, "Market cap", Str(doc["market_cap"]));
        Line(sb, "Volume", Str(doc["volume"]));
        Line(sb, "Avg volume 10d", Str(doc["avg_volume_10d"]));
        Line(sb, "50d average", Str(doc["avg_50d"]));
        sb.AppendLine();
    }

    private static void AppendRange52w(StringBuilder sb, JsonObject doc)
    {
        if (doc["week_52"] is not JsonObject w) return;
        sb.AppendLine("## 52-week range");
        Line(sb, "High", Str(w["high"]));
        Line(sb, "Low", Str(w["low"]));
        sb.AppendLine();
    }

    private static void AppendRatios(StringBuilder sb, JsonObject? r)
    {
        if (r is null) return;
        sb.AppendLine("## Ratios");
        Line(sb, "P/E", Str(r["pe"]));
        Line(sb, "EPS", Str(r["eps"]));
        Line(sb, "Dividend yield", Str(r["dividend_yield"]));
        Line(sb, "Beta", Str(r["beta"]));
        sb.AppendLine();
    }

    private static void AppendSentiment(StringBuilder sb, JsonObject? s)
    {
        if (s is null) return;
        sb.AppendLine("## Sentiment");
        Line(sb, "Sentiment score", Str(s["sentiment_score"]));
        Line(sb, "Confidence", Str(s["confidence"]));
        Line(sb, "Analyzer", Str(s["analyzer_type"]));
        Line(sb, "Trend", Str(s["sentiment_trend"]));
        Line(sb, "Growth sentiment", Str(s["growth_sentiment"]));
        Line(sb, "Dividend safety", Str(s["dividend_safety"]));
        Line(sb, "Articles (7d / 30d)", $"{Str(s["news_count_7d"])} / {Str(s["news_count_30d"])}");
        Line(sb, "Positive / Neutral / Negative",
            $"{Str(s["positive_count"])} / {Str(s["neutral_count"])} / {Str(s["negative_count"])}");
        Line(sb, "Key themes", Arr(s["key_themes"]));
        Line(sb, "Catalysts", Arr(s["catalysts"]));
        Line(sb, "Risks", Arr(s["risks"]));
        sb.AppendLine();
    }

    private static void AppendAnalystGuidance(StringBuilder sb, JsonArray? guidance)
    {
        if (guidance is null || guidance.Count == 0) return;
        sb.AppendLine("## Analyst guidance");
        foreach (JsonNode? node in guidance)
        {
            if (node is not JsonObject g) continue;
            sb.Append("- **")
              .Append(Str(g["fiscal_year"]));
            string q = Str(g["quarter"]);
            if (q is not "N/A" and not "") sb.Append(" Q").Append(q);
            sb.Append("** — rating: ").Append(Str(g["rating"]))
              .Append(" (").Append(Str(g["analyst_count"])).AppendLine(" analysts)");

            Sub(sb, "EPS (est / low / high)",
                $"{Str(g["eps_estimate"])} / {Str(g["eps_low"])} / {Str(g["eps_high"])}");
            Sub(sb, "Revenue (est / low / high)",
                $"{Str(g["revenue_estimate"])} / {Str(g["revenue_low"])} / {Str(g["revenue_high"])}");

            if (g["rating_distribution"] is JsonObject rd)
                Sub(sb, "Distribution",
                    $"strong_buy {Str(rd["strong_buy"])}, buy {Str(rd["buy"])}, hold {Str(rd["hold"])}, " +
                    $"sell {Str(rd["sell"])}, strong_sell {Str(rd["strong_sell"])}");

            Sub(sb, "Updated", Str(g["updated_date"]));
        }
        sb.AppendLine();
    }

    private static void AppendNews(StringBuilder sb, JsonArray? news)
    {
        if (news is null || news.Count == 0) return;
        sb.Append("## News (").Append(news.Count).AppendLine(")");
        foreach (JsonNode? node in news)
        {
            if (node is not JsonObject n) continue;
            sb.Append("### ").AppendLine(Str(n["title"]));
            Line(sb, "Date", Str(n["publish_date"]));
            Line(sb, "Source", Str(n["source"]));
            Line(sb, "Category", Str(n["category"]));
            Line(sb, "Sentiment", $"{Str(n["sentiment"])} (impact {Str(n["impact_score"])}, confidence {Str(n["confidence"])})");
            Line(sb, "Keywords", Arr(n["keywords"]));
            string content = Str(n["content"]);
            if (content is not "N/A" and not "") { Line(sb, "Summary", content); }
            Line(sb, "URL", Str(n["url"]));
            sb.AppendLine();
        }
    }

    // ---- helpers ----------------------------------------------------------

    private static void Line(StringBuilder sb, string label, string value) =>
        sb.Append("- **").Append(label).Append("** : ").AppendLine(value);

    private static void Sub(StringBuilder sb, string label, string value) =>
        sb.Append("  - ").Append(label).Append(" : ").AppendLine(value);

    /// <summary>Formats any JSON scalar as a display string; null/missing -> "N/A".</summary>
    private static string Str(JsonNode? n)
    {
        if (n is null) return "N/A";
        return n.GetValueKind() switch
        {
            JsonValueKind.Null => "N/A",
            JsonValueKind.String => n.GetValue<string>(),
            _ => n.ToString()
        };
    }

    /// <summary>Joins a JSON array of scalars into a comma-separated list.</summary>
    private static string Arr(JsonNode? n)
    {
        if (n is not JsonArray arr || arr.Count == 0) return "—";
        return string.Join(", ", arr.Select(Str));
    }

    /// <summary>Renders an epoch-millis value as an ISO-8601 UTC timestamp.</summary>
    private static string Epoch(JsonNode? n)
    {
        if (n is null || n.GetValueKind() != JsonValueKind.Number) return "N/A";
        if (!long.TryParse(n.ToString(), NumberStyles.Any, CultureInfo.InvariantCulture, out long ms))
            return Str(n);
        return DateTimeOffset.FromUnixTimeMilliseconds(ms)
            .UtcDateTime.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture);
    }
}
