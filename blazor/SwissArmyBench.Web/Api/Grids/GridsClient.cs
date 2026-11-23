namespace SwissArmyBench.Web.Api.Grids;

/// <summary>Grids (routes_grids.py, routes_datasets.py): the open grids, one grid's view and its steps, a column's
/// profile, the selection's numbers, the Key Finder, closing a table, the "+" tab's query, a table's connection.
/// The rows themselves go from the server into AG Grid directly.</summary>
public sealed class GridsClient
{
    private readonly ApiClient _api;

    public GridsClient(ApiClient api)
    {
        _api = api;
    }

    public async Task<IReadOnlyList<GridListItem>> ListAsync() => (await _api.GetAsync<GridsAnswer>("/grids")).Grids;

    public Task<GridInfo> InfoAsync(string grid) => _api.GetAsync<GridInfo>(Base(grid));

    /// <summary>A column's profile; `upto` profiles the data after that many steps (a step's preview).</summary>
    public Task<ColumnProfile> ProfileAsync(string grid, string column, int? upto = null) =>
        _api.GetAsync<ColumnProfile>($"{Base(grid)}/profile?column={ApiClient.Part(column)}{Upto(upto)}");

    public Task<TableProfile> TableProfileAsync(string grid, int? upto = null) =>
        _api.GetAsync<TableProfile>($"{Base(grid)}/profile{(upto is { } n ? $"?upto={n}" : string.Empty)}");

    private static string Upto(int? upto) => upto is { } n ? $"&upto={n}" : string.Empty;

    /// <summary>A column's values with their counts (the filter's checklist), those holding `search` when given.</summary>
    public Task<ValueList> ValuesAsync(string grid, string column, string search, int? upto)
    {
        var address = $"{Base(grid)}/values?column={ApiClient.Part(column)}";
        if (search.Length > 0)
        {
            address += $"&search={ApiClient.Part(search)}";
        }
        if (upto is { } before)
        {
            address += $"&upto={before}";
        }
        return _api.GetAsync<ValueList>(address);
    }

    /// <summary>A step added at the end: {kind, params}.</summary>
    public Task<GridInfo> AddStepAsync(string grid, string kind, object parameters) =>
        StepOpAsync(grid, new { op = "add", step = new { kind, @params = parameters } });

    public Task<GridInfo> DeleteStepAsync(string grid, int index) => StepOpAsync(grid, new { op = "delete", index });

    public Task<GridInfo> ToggleStepAsync(string grid, int index, bool enabled) => StepOpAsync(grid, new { op = "toggle", index, enabled });

    public Task<GridInfo> UndoAsync(string grid) => StepOpAsync(grid, new { op = "undo" });

    public Task<GridInfo> RedoAsync(string grid) => StepOpAsync(grid, new { op = "redo" });

    /// <summary>Every step at once (an edited step in its place), and the text matching when it changes.</summary>
    public Task<GridInfo> SaveStepsAsync(string grid, IEnumerable<GridStep> steps, TextMatching? settings = null)
    {
        var sent = steps.Select(s => new { id = s.Id, kind = s.Kind, @params = s.Params, enabled = s.Enabled }).ToList();
        object body = settings is null ? new { steps = sent, client = ApiClient.ClientId } : new { steps = sent, settings, client = ApiClient.ClientId };
        return _api.PostAsync<GridInfo>($"{Base(grid)}/steps", body);
    }

    /// <summary>Count, sum and average over the selection, counted by the server (rows never loaded too).</summary>
    public Task<SelectionStats> SelectionStatsAsync(string grid, SelectionDescriptor selection) =>
        _api.PostAsync<SelectionStats>($"{Base(grid)}/selection-stats?client={ApiClient.ClientId}", new { selection });

    /// <summary>Copy as code: the steps as one DuckDB query and as Python, verified against the grid.</summary>
    public Task<GridCode> CodeAsync(string grid) => _api.GetAsync<GridCode>($"{Base(grid)}/code");

    public Task<KeyFinderTargets> KeyFinderTargetsAsync(string grid) => _api.GetAsync<KeyFinderTargets>($"{Base(grid)}/key-finder");

    /// <summary>The likely join keys with another grid ("*": every other open grid), best first; the options are the
    /// Key Finder's (trim, ignore_case, max_length).</summary>
    public Task<KeyFinderResult> KeyFinderAsync(string grid, string target, object? options = null) =>
        _api.PostAsync<KeyFinderResult>($"{Base(grid)}/key-finder", new { target, options = options ?? new Dictionary<string, object>() });

    /// <summary>A pair's values: the ones both columns hold, and the ones of this column the other lacks.</summary>
    public Task<KeySample> KeySampleAsync(string grid, KeyPair pair, object options) =>
        _api.PostAsync<KeySample>($"{Base(grid)}/key-finder/sample", new { target = pair.TargetGrid, source_column = pair.SourceColumn, target_column = pair.TargetColumn, options });

    /// <summary>The address of the grid's export (a download, or saved in the export folder with save=1).</summary>
    public static string ExportAddress(string grid, IReadOnlyDictionary<string, string> options) =>
        $"{Base(grid)}/export?{string.Join("&", options.Select(o => $"{o.Key}={ApiClient.Part(o.Value)}"))}";

    /// <summary>The export saved in the export folder (~/.swissarmybench/exports): the server's words.</summary>
    public Task<ExportSaved> SaveExportAsync(string grid, IReadOnlyDictionary<string, string> options) =>
        _api.GetAsync<ExportSaved>(ExportAddress(grid, options.Append(new("save", "1")).ToDictionary()));

    /// <summary>Close the table (its dataset and every grid on it).</summary>
    public Task CloseAsync(string dataset) => _api.DeleteAsync<ClosedTable>($"/datasets/{ApiClient.Part(dataset)}");

    /// <summary>A new table from a DuckDB query (the "+" tab's): its grid.</summary>
    public Task<MadeTable> QueryAsync(string name, string sql) => _api.PostAsync<MadeTable>($"/datasets/{ApiClient.Part(name)}/query", new { sql });

    /// <summary>This view, after its steps, as a sandbox variant (its own name; it never writes back).</summary>
    public Task<MadeTable> SandboxVariantAsync(string dataset) =>
        _api.PostAsync<MadeTable>("/sandbox/tables/variant", new { from = "grid", table = dataset });

    public Task<TableConnection> ConnectionOfAsync(string table) => _api.GetAsync<TableConnection>($"/tables/{ApiClient.Part(table)}/connection");

    /// <summary>The table read from another connection, its steps kept; with a place (a pick) or SQL (a reviewed
    /// query) when the first answer asked for one.</summary>
    public Task<ConnectionSwap> SwapConnectionAsync(string table, string to, SwapPlace? place = null, string? sql = null) =>
        _api.PostAsync<ConnectionSwap>($"/tables/{ApiClient.Part(table)}/connection", (place, sql) switch
        {
            ({ } p, _) => new { to, place = new { database = p.Database, schema = p.Schema, table = p.Table } },
            (_, { } q) => new { to, sql = q },
            _ => (object)new { to },
        });

    /// <summary>A schema's tables in a connection's catalog (the swap's pick).</summary>
    public async Task<IReadOnlyList<SwapPlace>> CatalogTablesAsync(string connection, SwapSchema schema)
    {
        var address = $"/catalogs/{ApiClient.Part(connection)}/tables?schema={ApiClient.Part(schema.Schema)}&limit=500";
        if (schema.Database.Length > 0)
        {
            address += $"&database={ApiClient.Part(schema.Database)}";
        }
        return (await _api.GetAsync<CatalogTablesAnswer>(address)).Tables;
    }

    public async Task<IReadOnlyList<CodeReference>> ReferencesAsync(string connection) =>
        (await _api.GetAsync<ReferencesAnswer>($"/connections/{ApiClient.Part(connection)}/references")).References;

    public Task<RepointAnswer> RepointAsync(string from, string to, IEnumerable<CodeReference> picks) =>
        _api.PostAsync<RepointAnswer>($"/connections/{ApiClient.Part(from)}/repoint", new { to, picks = picks.Select(p => new { document = p.Document, cell = p.Cell }) });

    public Task UndoSwapAsync(string table) => _api.PostAsync($"/tables/{ApiClient.Part(table)}/connection/undo");

    private static string Base(string grid) => $"/grids/{ApiClient.Part(grid)}";

    private Task<GridInfo> StepOpAsync(string grid, object body) => _api.PostAsync<GridInfo>($"{Base(grid)}/step-ops", body);
}
