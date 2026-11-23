namespace SwissArmyBench.Web.Api.Sandbox;

/// <summary>The project's sandbox (routes_sandbox.py): its tables, Reset, the baseline, checkpoints, variants and
/// mocks.</summary>
public sealed class SandboxClient
{
    private readonly ApiClient _api;

    public SandboxClient(ApiClient api)
    {
        _api = api;
    }

    public Task<SandboxState> StateAsync(string sort, string order) =>
        _api.GetAsync<SandboxState>($"/sandbox?sort={ApiClient.Part(sort)}&order={ApiClient.Part(order)}");

    /// <summary>A table added: from an open table, a file or its columns (the body as the dialog makes it).</summary>
    public Task AddAsync(IReadOnlyDictionary<string, object?> given) => _api.PostAsync("/sandbox/tables", given);

    public Task RemoveAsync(string table) => _api.PostAsync("/sandbox/tables/remove", new { table });

    public Task OpenAsync(string table) => _api.PostAsync("/sandbox/tables/open", new { table });

    /// <summary>Every table back to its baseline, or one table alone.</summary>
    public Task ResetAsync(string? table = null) => _api.PostAsync("/sandbox/reset", table is null ? new { } : new { table });

    public Task BaselineAsync() => _api.PostAsync("/sandbox/baseline", new { });

    public Task SaveCheckpointAsync(string name) => _api.PostAsync("/sandbox/checkpoints", new { name, action = "save" });

    public Task DeleteCheckpointAsync(string name) => _api.PostAsync("/sandbox/checkpoints", new { name, action = "delete" });

    public Task RestoreAsync(string name) => _api.PostAsync("/sandbox/checkpoints/restore", new { name });

    /// <summary>A table's rows mocked as a connection's kind (null: the plain DuckDB client).</summary>
    public Task MockAsync(string table, string? connection) => _api.PostAsync("/sandbox/tables/mock", new { table, connection });

    /// <summary>A copy of an open table's view (from "grid") or a structure's records (from "structure").</summary>
    public Task<MadeVariant> VariantAsync(string from, string origin, string? name, string? path = null) =>
        _api.PostAsync<MadeVariant>(
            "/sandbox/tables/variant",
            new Dictionary<string, object?> { ["from"] = from, [from == "grid" ? "table" : "structure"] = origin, ["path"] = path, ["name"] = name });
}
