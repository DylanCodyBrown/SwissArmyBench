namespace SwissArmyBench.Web.Api.Connections;

/// <summary>Connections (routes_connections.py, routes_connection_tables.py, routes_found_connections.py,
/// routes_connection_colours.py) and the blade routes a connection shares (routes_blades.py: fill, inspect, test,
/// refresh, install, remove).</summary>
public sealed class ConnectionsClient
{
    private readonly ApiClient _api;

    public ConnectionsClient(ApiClient api)
    {
        _api = api;
    }

    private static string Path(string name) => $"/connections/{ApiClient.Part(name)}";

    public async Task<IReadOnlyList<ConnectionCard>> CardsAsync() => (await _api.GetAsync<CardsAnswer>("/connections/usage")).Connections;

    public async Task<IReadOnlyList<ListedConnection>> ListedAsync() => (await _api.GetAsync<ListedAnswer>("/connections")).Connections;

    public Task<ConnectionUsage> UsageAsync(string name) => _api.GetAsync<ConnectionUsage>($"{Path(name)}/usage");

    public Task<ConnectionTree> TreeAsync(string name) => _api.GetAsync<ConnectionTree>($"{Path(name)}/tree");

    public async Task<IReadOnlyList<ConnectionForm>> FormsAsync() => (await _api.GetAsync<FormsAnswer>("/connections/types")).Types;

    public Task<ConnectionForm> FormAsync(string name) => _api.GetAsync<ConnectionForm>(Path(name));

    /// <summary>A value written into the code at one field (by its place in the code); the code and fields again. A box
    /// sends its whole text ({text}: a value, or ${NAME} the code then reads where it runs); a choice its value.</summary>
    public Task<FilledCode> FillAsync(string code, IReadOnlyDictionary<string, object?> values, string? template, string? name) =>
        _api.PostAsync<FilledCode>("/blades/fill", new { code, values, template, name });

    /// <summary>A code's settings, passwords and packages read again (with ast, never run).</summary>
    public Task<InspectedCode> InspectAsync(string code, string? template, string? name) =>
        _api.PostAsync<InspectedCode>("/blades/inspect", new { code, template, name });

    /// <summary>A password pointed at a variable: the code then asks for secret("NAME").</summary>
    public Task<PointedAnswer> PointAtAsync(string code, string secret, string variable) =>
        _api.PostAsync<PointedAnswer>("/connections/source", new { code, secret, from = "env", env = variable });

    /// <summary>A typed password kept as a keyring variable of this computer.</summary>
    public Task KeepInKeyringAsync(string variable, string value) =>
        _api.PutAsync("/variables", new { name = variable, value, from = "keyring" });

    /// <summary>The variables this computer has (a vault's form says a name another source gives).</summary>
    public async Task<IReadOnlyList<TakenVariable>> TakenAsync() => (await _api.GetAsync<TakenVariables>("/variables")).Variables;

    /// <summary>A vault's secret names (never a value), read with the form's code.</summary>
    public Task<VaultNames> VaultSecretsAsync(IReadOnlyDictionary<string, object?> form) =>
        _api.PostAsync<VaultNames>("/connections/vaults/secrets", form);

    /// <summary>The environment variables a Python connection's three boxes read (found with ast, never run).</summary>
    public async Task<IReadOnlyList<VariableRead>> VariablesAsync(string code, string tables, string read) =>
        (await _api.PostAsync<VariableReads>("/connections/variables", new { code, tables, read })).Variables;

    /// <summary>Run the form's code, not saved, with the passwords typed into it.</summary>
    public Task<TestAnswer> TestAsync(IReadOnlyDictionary<string, object?> form) => _api.PostAsync<TestAnswer>("/connections/test", form);

    public Task SaveAsync(IReadOnlyDictionary<string, object?> form) => _api.PostAsync("/connections", form);

    public Task ChangeAsync(string name, IReadOnlyDictionary<string, object?> form) => _api.PutAsync(Path(name), form);

    public Task<RemovedAnswer> RemoveAsync(string name) => _api.DeleteAsync<RemovedAnswer>($"/blades/{ApiClient.Part(name)}");

    /// <summary>Does it work? Its code run in a child process (a saved connection's Test).</summary>
    public Task<TestAnswer> CheckAsync(string name) => _api.PostAsync<TestAnswer>($"/blades/{ApiClient.Part(name)}/test");

    /// <summary>Its tables listed again (the catalog loaded now).</summary>
    public Task<RefreshAnswer> RefreshAsync(string name) => _api.PostAsync<RefreshAnswer>($"/blades/{ApiClient.Part(name)}/refresh");

    /// <summary>Packages installed into the app's Python.</summary>
    public Task InstallAsync(IReadOnlyList<string> packages) => _api.PostAsync("/blades/install", new { packages });

    /// <summary>A table opened as a grid (Open).</summary>
    public Task<OpenAnswer> OpenAsync(string name, TreeTable table) =>
        _api.PostAsync<OpenAnswer>($"{Path(name)}/open", new { database = table.Database, schema = table.Schema, table = table.Table });

    /// <summary>A file connection's file as a grid; a workbook answers its sheets first, then each opens by name.</summary>
    public Task<OpenAnswer> OpenFileAsync(string name, string? sheet = null) =>
        _api.PostAsync<OpenAnswer>($"{Path(name)}/open", sheet is null ? new { } : new { table = sheet });

    public Task<TablePreview> PreviewAsync(string name, TreeTable table) =>
        _api.PostAsync<TablePreview>($"{Path(name)}/preview", new { database = table.Database, schema = table.Schema, table = table.Table });

    /// <summary>Every table of one dataset or schema, each its own grid.</summary>
    public Task<OpenedDataset> OpenDatasetAsync(string name, string dataset) =>
        _api.PostAsync<OpenedDataset>($"{Path(name)}/open-dataset", new { dataset });

    /// <summary>A Power BI dataset's relationships, or SQL Server's foreign keys, merged into the model.</summary>
    public Task<RelationshipsAnswer> RelationshipsAsync(string name, string? dataset = null) =>
        _api.PostAsync<RelationshipsAnswer>($"{Path(name)}/relationships", dataset is null ? new { } : new { dataset });

    /// <summary>A Dataverse connection saved for its Web API moved to its SQL endpoint.</summary>
    public Task SqlEndpointAsync(string name) => _api.PostAsync($"{Path(name)}/sql-endpoint");

    /// <summary>The app's earlier SQL Server code made again on mssql-python, its settings kept.</summary>
    public Task UpdateDriverAsync(string name) => _api.PostAsync($"{Path(name)}/update-driver");

    public async Task<IReadOnlyList<AccessBy>> AccessAsync(string name) => (await _api.GetAsync<AccessAnswer>($"{Path(name)}/access")).Access;

    public Task CheckRegistrationAsync(string registration) => _api.PostAsync($"/app-registrations/{ApiClient.Part(registration)}/check");

    public Task<ColourListing> ColoursAsync() => _api.GetAsync<ColourListing>("/connection-colours");

    /// <summary>A connection's colour chosen (null: the next free one); the server refuses the rail's colours.</summary>
    public Task<ColourListing> SetColourAsync(string name, string? colour) =>
        _api.PutAsync<ColourListing>($"/connection-colours/{ApiClient.Part(name)}", new { colour });

    /// <summary>A new %%sql cell in the Notebooks page's notebook.</summary>
    public Task QueryInNotebookAsync(string source) =>
        _api.PostAsync("/workbench/window", new { command = "cell.insertBelow", args = new { kind = "sql", source }, page = "notebooks" });

    public Task<FoundList> FindAsync(CancellationToken cancel = default) => _api.PostAsync<FoundList>("/connections/found", new { }, cancel);

    public Task CancelFindAsync() => _api.PostAsync("/connections/found/cancel", new { });

    public Task<ImportAnswer> ImportAsync(IReadOnlyList<string> ids) => _api.PostAsync<ImportAnswer>("/connections/found/import", new { ids });
}
