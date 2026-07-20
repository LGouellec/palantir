namespace Palantir.FlinkProxy;

/// <summary>
/// Configuration for the CosmosDB backing store that holds one document per
/// NASDAQ ticker (the "companies" container). Bound from the "Cosmos" section
/// of appsettings.json, overridable with env vars (e.g. Cosmos__Key).
/// </summary>
public sealed class CosmosOptions
{
    public const string SectionName = "Cosmos";

    /// <summary>Account endpoint </summary>
    public string Endpoint { get; set; } = "";

    /// <summary>Account primary/secondary key.</summary>
    public string Key { get; set; } = "";

    /// <summary>Database name </summary>
    public string Database { get; set; } = "palantir-db";

    /// <summary>Container name holding the company documents.</summary>
    public string Container { get; set; } = "companies";

    /// <summary>
    /// Name of the document property that holds the ticker (the search key).
    /// The Flink external table's search column is matched against this.
    /// </summary>
    public string KeyField { get; set; } = "ticker";
}
