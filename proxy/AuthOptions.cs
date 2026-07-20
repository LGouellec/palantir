namespace Palantir.FlinkProxy;

public enum AuthScheme
{
    /// <summary>No authentication — the endpoint is open (default).</summary>
    None,

    /// <summary>HTTP Basic — matches Confluent CREATE CONNECTION 'authentication.type' = 'basic'.</summary>
    Basic,

    /// <summary>Bearer token — matches Confluent CREATE CONNECTION 'authentication.type' = 'bearer'.</summary>
    Bearer,

    /// <summary>API key sent in a custom header (default X-API-Key).</summary>
    ApiKey
}

/// <summary>
/// Authentication expected on the REST endpoint, aligned with the
/// `authentication.*` options of Flink's REST CREATE CONNECTION. Bound from the
/// "Auth" section; secrets are overridable with env vars (e.g. Auth__Password).
/// </summary>
public sealed class AuthOptions
{
    public const string SectionName = "Auth";

    public AuthScheme Type { get; set; } = AuthScheme.None;

    /// <summary>Basic auth username (Type = Basic).</summary>
    public string Username { get; set; } = "";

    /// <summary>Basic auth password (Type = Basic).</summary>
    public string Password { get; set; } = "";

    /// <summary>Bearer token (Type = Bearer).</summary>
    public string Token { get; set; } = "";

    /// <summary>Name of the header carrying the API key (Type = ApiKey).</summary>
    public string ApiKeyHeader { get; set; } = "X-API-Key";

    /// <summary>Expected API key value (Type = ApiKey).</summary>
    public string ApiKey { get; set; } = "";
}
