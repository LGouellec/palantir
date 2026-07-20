using System.Text.RegularExpressions;
using System.Text.Json.Nodes;

namespace Palantir.FlinkProxy;

/// <summary>
/// Pulls candidate ticker keys out of whatever JSON body Flink's REST external
/// table connector sends. The exact request shape emitted by KEY_SEARCH_AGG is
/// not contractually documented and may be a bare string, an array, or an object
/// keyed by the search column, so we stay tolerant: collect every scalar leaf and
/// keep the ones that look like a NASDAQ ticker.
/// </summary>
public static partial class KeyExtractor
{
    // Tickers: 1-6 uppercase letters, optional class suffix like BRK.B.
    [GeneratedRegex(@"^[A-Z]{1,6}(\.[A-Z]{1,2})?$")]
    private static partial Regex TickerShape();

    public static IReadOnlyList<string> Extract(JsonNode? body, string? preferredField)
    {
        var found = new List<string>();
        Collect(body, preferredField, found);

        return found
            .Where(v => TickerShape().IsMatch(v))
            .Distinct(StringComparer.Ordinal)
            .ToList();
    }

    private static void Collect(JsonNode? node, string? preferredField, List<string> sink)
    {
        switch (node)
        {
            case JsonObject obj:
                // If the payload names the search column explicitly, trust it first.
                if (preferredField is not null &&
                    obj.TryGetPropertyValue(preferredField, out JsonNode? keyed) &&
                    keyed is JsonValue)
                {
                    AddScalar(keyed, sink);
                    return;
                }
                foreach (var kvp in obj)
                    Collect(kvp.Value, preferredField, sink);
                break;

            case JsonArray arr:
                foreach (JsonNode? item in arr)
                    Collect(item, preferredField, sink);
                break;

            case JsonValue val:
                AddScalar(val, sink);
                break;
        }
    }

    private static void AddScalar(JsonNode node, List<string> sink)
    {
        // GetValue<string>() only works for JSON strings; fall back to ToString()
        // for numbers so numeric keys still flow through.
        if (node is JsonValue val && val.TryGetValue(out string? s) && s is not null)
            sink.Add(s.Trim());
        else
            sink.Add(node.ToString().Trim());
    }
}
