using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.AspNetCore.Mvc;

namespace Palantir.FlinkProxy.Controllers;

/// <summary>
/// HTTP surface consumed by Flink's KEY_SEARCH_AGG over a REST external table.
///
/// Flink POSTs a JSON body containing the search key(s); we accept any JSON shape,
/// resolve the matching company document(s) from CosmosDB, and return a JSON array.
/// Confluent Cloud accepts either a single JSON node or an array of nodes and maps
/// the fields to the external table's columns, so an array is the natural fit for
/// an aggregating key search.
/// </summary>
[ApiController]
[Route("companies")]
public sealed class KeySearchController : ControllerBase
{
    private readonly ICompanyRepository _repository;
    private readonly CosmosOptions _options;
    private readonly ILogger<KeySearchController> _logger;

    public KeySearchController(
        ICompanyRepository repository,
        CosmosOptions options,
        ILogger<KeySearchController> logger)
    {
        _repository = repository;
        _options = options;
        _logger = logger;
    }

    /// <summary>Primary endpoint invoked by KEY_SEARCH_AGG.</summary>
    [HttpPost("key-search")]
    [Consumes("application/json")]
    [Produces("application/json")]
    public async Task<IActionResult> KeySearch(CancellationToken cancellationToken)
    {
        string raw;
        using (var reader = new StreamReader(Request.Body))
            raw = await reader.ReadToEndAsync(cancellationToken);

        // Log the raw body once so the exact Flink request shape can be confirmed
        // against a live statement and the extraction tightened if needed.
        _logger.LogDebug("KEY_SEARCH_AGG raw request body: {Body}", raw);

        JsonNode? body = null;
        if (!string.IsNullOrWhiteSpace(raw))
        {
            try
            {
                body = JsonNode.Parse(raw);
            }
            catch (JsonException ex)
            {
                _logger.LogWarning(ex, "Request body was not valid JSON: {Body}", raw);
                return BadRequest(new { error = "invalid JSON body", detail = ex.Message });
            }
        }

        var keys = KeyExtractor.Extract(body, _options.KeyField);
        if (keys.Count == 0)
        {
            _logger.LogWarning("No ticker key found in request body: {Body}", raw);
            return Ok(new JsonArray());
        }

        IReadOnlyList<JsonNode> docs = await _repository.FindByKeysAsync(keys, cancellationToken);
        return new JsonResult(docs);
    }

    /// <summary>
    /// Same key lookup as <see cref="KeySearch"/> but returns, per matched
    /// company, a Markdown briefing summarising every field of the document.
    /// Shape: <c>[{ "ticker", "name", "report" }]</c> — the <c>report</c> column
    /// (STRING) is meant to feed an LLM (e.g. via AI_COMPLETE downstream).
    /// </summary>
    [HttpPost("report")]
    [Consumes("application/json")]
    [Produces("application/json")]
    public async Task<IActionResult> Report(CancellationToken cancellationToken)
    {
        string raw;
        using (var reader = new StreamReader(Request.Body))
            raw = await reader.ReadToEndAsync(cancellationToken);

        _logger.LogDebug("report raw request body: {Body}", raw);

        JsonNode? body = null;
        if (!string.IsNullOrWhiteSpace(raw))
        {
            try { body = JsonNode.Parse(raw); }
            catch (JsonException ex)
            {
                _logger.LogWarning(ex, "Request body was not valid JSON: {Body}", raw);
                return BadRequest(new { error = "invalid JSON body", detail = ex.Message });
            }
        }

        var keys = KeyExtractor.Extract(body, _options.KeyField);
        if (keys.Count == 0)
        {
            _logger.LogWarning("No ticker key found in request body: {Body}", raw);
            return Ok(new JsonArray());
        }

        IReadOnlyList<JsonNode> docs = await _repository.FindByKeysAsync(keys, cancellationToken);

        var reports = new JsonArray();
        foreach (JsonNode doc in docs)
        {
            if (doc is not JsonObject obj) continue;
            reports.Add(new JsonObject
            {
                ["ticker"] = obj["ticker"]?.DeepClone(),
                ["name"] = obj["name"]?.DeepClone(),
                ["report"] = ReportBuilder.BuildMarkdown(obj)
            });
        }

        return new JsonResult(reports);
    }

    /// <summary>
    /// Convenience GET lookup (single ticker via path) for manual testing:
    /// <c>curl http://localhost:8080/companies/AMD</c>.
    /// </summary>
    [HttpGet("{ticker}")]
    [Produces("application/json")]
    public async Task<IActionResult> GetByTicker(string ticker, CancellationToken cancellationToken)
    {
        var docs = await _repository.FindByKeysAsync(new[] { ticker.ToUpperInvariant() }, cancellationToken);
        return new JsonResult(docs);
    }

    /// <summary>
    /// Convenience GET returning the raw Markdown briefing for one ticker:
    /// <c>curl http://localhost:8080/companies/report/SPCX</c>.
    /// </summary>
    [HttpGet("report/{ticker}")]
    [Produces("text/markdown")]
    public async Task<IActionResult> ReportByTicker(string ticker, CancellationToken cancellationToken)
    {
        var docs = await _repository.FindByKeysAsync(new[] { ticker.ToUpperInvariant() }, cancellationToken);
        if (docs.Count == 0 || docs[0] is not JsonObject obj)
            return NotFound();

        return Content(ReportBuilder.BuildMarkdown(obj), "text/markdown");
    }
}
