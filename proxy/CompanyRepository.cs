using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Azure.Cosmos;

namespace Palantir.FlinkProxy;

public interface ICompanyRepository
{
    /// <summary>
    /// Returns the company documents whose key field matches any of the given
    /// tickers. Order is not guaranteed. Missing tickers are simply absent.
    /// </summary>
    Task<IReadOnlyList<JsonNode>> FindByKeysAsync(
        IReadOnlyCollection<string> tickers,
        CancellationToken cancellationToken);
}

public sealed class CompanyRepository : ICompanyRepository
{
    // CosmosDB system properties we strip before handing documents to Flink.
    private static readonly HashSet<string> SystemProps = new(StringComparer.Ordinal)
    {
        "_rid", "_self", "_etag", "_attachments", "_ts", "_lsn"
    };

    private readonly Container _container;
    private readonly CosmosOptions _options;
    private readonly ILogger<CompanyRepository> _logger;

    public CompanyRepository(
        CosmosClient client,
        CosmosOptions options,
        ILogger<CompanyRepository> logger)
    {
        _options = options;
        _logger = logger;
        _container = client.GetContainer(options.Database, options.Container);
    }

    public async Task<IReadOnlyList<JsonNode>> FindByKeysAsync(
        IReadOnlyCollection<string> tickers,
        CancellationToken cancellationToken)
    {
        if (tickers.Count == 0)
            return Array.Empty<JsonNode>();

        // WHERE ARRAY_CONTAINS(@keys, c.<keyField>) lets us resolve a whole
        // batch of tickers in a single cross-partition query.
        var query = new QueryDefinition(
                $"SELECT * FROM c WHERE ARRAY_CONTAINS(@keys, c.{_options.KeyField})")
            .WithParameter("@keys", tickers);

        var results = new List<JsonNode>(tickers.Count);

        using FeedIterator iterator = _container.GetItemQueryStreamIterator(query);
        while (iterator.HasMoreResults)
        {
            using ResponseMessage response = await iterator.ReadNextAsync(cancellationToken);
            response.EnsureSuccessStatusCode();

            using JsonDocument page = await JsonDocument.ParseAsync(
                response.Content, cancellationToken: cancellationToken);

            if (!page.RootElement.TryGetProperty("Documents", out JsonElement docs))
                continue;

            foreach (JsonElement doc in docs.EnumerateArray())
            {
                if (JsonNode.Parse(doc.GetRawText()) is JsonObject obj)
                {
                    foreach (string prop in SystemProps)
                        obj.Remove(prop);
                    results.Add(obj);
                }
            }
        }

        _logger.LogInformation(
            "Resolved {Found}/{Requested} tickers from {Container}",
            results.Count, tickers.Count, _options.Container);

        return results;
    }
}
