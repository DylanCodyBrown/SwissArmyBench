namespace SwissArmyBench.Web.Api.Connections;

/// <summary>Connections (routes_connections.py, routes_connection_tables.py, routes_found_connections.py) and the
/// blade routes a connection shares (routes_blades.py: fill, test, refresh, remove).</summary>
public sealed class ConnectionsClient
{
    private readonly ApiClient _api;

    public ConnectionsClient(ApiClient api)
    {
        _api = api;
    }

    public async Task<IReadOnlyList<ConnectionCard>> CardsAsync() => (await _api.GetAsync<CardsAnswer>("/connections/usage")).Connections;

    public Task<ConnectionUsage> UsageAsync(string name) => _api.GetAsync<ConnectionUsage>($"/connections/{ApiClient.Part(name)}/usage");

    public Task<ConnectionTree> TreeAsync(string name) => _api.GetAsync<ConnectionTree>($"/connections/{ApiClient.Part(name)}/tree");

    public async Task<IReadOnlyList<ConnectionForm>> FormsAsync() => (await _api.GetAsync<FormsAnswer>("/connections/types")).Types;

    public Task<ConnectionForm> FormAsync(string name) => _api.GetAsync<ConnectionForm>($"/connections/{ApiClient.Part(name)}");

    /// <summary>A value written into the code at one field (by its place in the code); the code and fields again.</summary>
    public Task<FilledCode> FillAsync(string code, string fieldId, object value, string? template, string? name) =>
        _api.PostAsync<FilledCode>("/blades/fill", new { code, values = new Dictionary<string, object> { [fieldId] = value }, template, name });

    /// <summary>Run the form's code, not saved, with the passwords typed into it.</summary>
    /// <summary>The environment variables a Python connection's three boxes read (found with ast, never run).</summary>
    public async Task<IReadOnlyList<VariableRead>> VariablesAsync(string code, string tables, string read) =>
        (await _api.PostAsync<VariableReads>("/connections/variables", new { code, tables, read })).Variables;

    public Task<TestAnswer> TestAsync(IReadOnlyDictionary<string, object?> form) => _api.PostAsync<TestAnswer>("/connections/test", form);

    public Task SaveAsync(IReadOnlyDictionary<string, object?> form) => _api.PostAsync("/connections", form);

    public Task ChangeAsync(string name, IReadOnlyDictionary<string, object?> form) =>
        _api.PutAsync($"/connections/{ApiClient.Part(name)}", form);

    public Task RemoveAsync(string name) => _api.DeleteAsync($"/blades/{ApiClient.Part(name)}");

    /// <summary>Does it work? Its code run in a child process (a saved connection's Test).</summary>
    public Task CheckAsync(string name) => _api.PostAsync($"/blades/{ApiClient.Part(name)}/test");

    /// <summary>Its tables listed again (the catalog loaded now).</summary>
    public Task RefreshAsync(string name) => _api.PostAsync($"/blades/{ApiClient.Part(name)}/refresh");

    /// <summary>A table opened as a grid (Open), its first rows or all of them.</summary>
    public Task OpenAsync(string name, TreeTable table) =>
        _api.PostAsync($"/connections/{ApiClient.Part(name)}/open", new { database = table.Database, schema = table.Schema, table = table.Table });

    public Task<FoundList> FindAsync() => _api.PostAsync<FoundList>("/connections/found", new { hints = true });

    public Task CancelFindAsync() => _api.PostAsync("/connections/found/cancel");

    public Task<ImportAnswer> ImportAsync(IReadOnlyList<string> ids) => _api.PostAsync<ImportAnswer>("/connections/found/import", new { ids });
}
