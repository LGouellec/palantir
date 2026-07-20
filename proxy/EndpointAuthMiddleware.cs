using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;

namespace Palantir.FlinkProxy;

/// <summary>
/// Validates the incoming <c>Authorization</c> header against the configured
/// scheme before requests reach the controllers. Mirrors the credentials set in
/// Flink's REST CREATE CONNECTION so KEY_SEARCH_AGG calls authenticate cleanly.
/// The health probe is always left open.
/// </summary>
public sealed class EndpointAuthMiddleware
{
    private readonly RequestDelegate _next;
    private readonly AuthOptions _options;
    private readonly ILogger<EndpointAuthMiddleware> _logger;

    // Precomputed expected credential values.
    private readonly string _expectedBasic;
    private readonly string _expectedBearer;

    public EndpointAuthMiddleware(
        RequestDelegate next,
        AuthOptions options,
        ILogger<EndpointAuthMiddleware> logger)
    {
        _next = next;
        _options = options;
        _logger = logger;

        _expectedBasic = Convert.ToBase64String(
            Encoding.UTF8.GetBytes($"{options.Username}:{options.Password}"));
        _expectedBearer = options.Token;

        if (options.Type == AuthScheme.Basic && string.IsNullOrEmpty(options.Password))
            _logger.LogWarning("Auth:Type is Basic but no password is configured.");
        if (options.Type == AuthScheme.Bearer && string.IsNullOrEmpty(options.Token))
            _logger.LogWarning("Auth:Type is Bearer but no token is configured.");
        if (options.Type == AuthScheme.ApiKey && string.IsNullOrEmpty(options.ApiKey))
            _logger.LogWarning("Auth:Type is ApiKey but no ApiKey is configured.");
    }

    public async Task InvokeAsync(HttpContext context)
    {
        // Open endpoints (health probe) and the no-auth mode short-circuit.
        if (_options.Type == AuthScheme.None ||
            context.Request.Path.StartsWithSegments("/healthz"))
        {
            await _next(context);
            return;
        }

        if (TryAuthenticate(context))
        {
            await _next(context);
            return;
        }

        _logger.LogWarning("Rejected unauthenticated request to {Path}", context.Request.Path);
        context.Response.StatusCode = StatusCodes.Status401Unauthorized;
        if (_options.Type is AuthScheme.Basic or AuthScheme.Bearer)
            context.Response.Headers.WWWAuthenticate = _options.Type.ToString();
        await context.Response.WriteAsJsonAsync(new { error = "unauthorized" });
    }

    private bool TryAuthenticate(HttpContext context)
    {
        // API key lives in a dedicated header, not in Authorization.
        if (_options.Type == AuthScheme.ApiKey)
        {
            return context.Request.Headers.TryGetValue(_options.ApiKeyHeader, out var provided) &&
                   provided.Count == 1 &&
                   FixedTimeEquals(provided[0]!, _options.ApiKey);
        }

        if (!AuthenticationHeaderValue.TryParse(
                context.Request.Headers.Authorization, out AuthenticationHeaderValue? header) ||
            header.Parameter is null)
        {
            return false;
        }

        return _options.Type switch
        {
            AuthScheme.Basic =>
                string.Equals(header.Scheme, "Basic", StringComparison.OrdinalIgnoreCase) &&
                FixedTimeEquals(header.Parameter, _expectedBasic),
            AuthScheme.Bearer =>
                string.Equals(header.Scheme, "Bearer", StringComparison.OrdinalIgnoreCase) &&
                FixedTimeEquals(header.Parameter, _expectedBearer),
            _ => false
        };
    }

    /// <summary>Length-safe, constant-time string comparison for secrets.</summary>
    private static bool FixedTimeEquals(string a, string b) =>
        CryptographicOperations.FixedTimeEquals(
            Encoding.UTF8.GetBytes(a), Encoding.UTF8.GetBytes(b));
}
