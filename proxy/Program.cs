using Azure;
using Microsoft.Azure.Cosmos;
using Palantir.FlinkProxy;

var builder = WebApplication.CreateBuilder(args);

// ---- Options -------------------------------------------------------------
var cosmosOptions = builder.Configuration
    .GetSection(CosmosOptions.SectionName)
    .Get<CosmosOptions>() ?? new CosmosOptions();

if (string.IsNullOrWhiteSpace(cosmosOptions.Endpoint) || string.IsNullOrWhiteSpace(cosmosOptions.Key))
    throw new InvalidOperationException(
        "Cosmos:Endpoint and Cosmos:Key must be configured (appsettings.json or env vars Cosmos__Endpoint / Cosmos__Key).");

builder.Services.AddSingleton(cosmosOptions);

var authOptions = builder.Configuration
    .GetSection(AuthOptions.SectionName)
    .Get<AuthOptions>() ?? new AuthOptions();
builder.Services.AddSingleton(authOptions);

// ---- CosmosDB client (singleton, thread-safe) ----------------------------
builder.Services.AddSingleton(_ => new CosmosClient(
    cosmosOptions.Endpoint,
    new AzureKeyCredential(cosmosOptions.Key),
    new CosmosClientOptions
    {
        // Gateway mode is friendlier to containers/egress-restricted networks.
        ConnectionMode = ConnectionMode.Gateway,
        ApplicationName = "flink-proxy"
    }));

builder.Services.AddSingleton<ICompanyRepository, CompanyRepository>();
builder.Services.AddControllers();

var app = builder.Build();

app.UseMiddleware<EndpointAuthMiddleware>();

app.MapControllers();
app.MapGet("/healthz", () => Results.Ok(new { status = "ok" }));

app.Run();
