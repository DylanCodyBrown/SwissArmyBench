using System.Text.Json;

namespace SwissArmyBench.Web.Api.Grids;

/// <summary>Grids (routes_grids.py, routes_datasets.py): the open grids, one grid's view and its steps, a column's
/// profile, closing a table, the "+" tab's query. The rows themselves go from the server into AG Grid directly.</summary>
public sealed class GridsClient
{
    private readonly ApiClient _api;

    public GridsClient(ApiClient api)
    {
        _api = api;
    }

    public async Task<IReadOnlyList<GridListItem>> ListAsync() => (await _api.GetAsync<GridsAnswer>("/grids")).Grids;

    public Task<GridInfo> InfoAsync(string grid) => _api.GetAsync<GridInfo>($"/grids/{ApiClient.Part(grid)}");

    public Task<ColumnProfile> ProfileAsync(string grid, string column) =>
        _api.GetAsync<ColumnProfile>($"/grids/{ApiClient.Part(grid)}/profile?column={ApiClient.Part(column)}");

    /// <summary>A step added at the end: {kind, params}.</summary>
    public Task<GridInfo> AddStepAsync(string grid, string kind, object parameters) =>
        StepOpAsync(grid, new { op = "add", step = new { kind, @params = parameters } });

    public Task<GridInfo> DeleteStepAsync(string grid, int index) => StepOpAsync(grid, new { op = "delete", index });

    public Task<GridInfo> ToggleStepAsync(string grid, int index, bool enabled) => StepOpAsync(grid, new { op = "toggle", index, enabled });

    public Task<GridInfo> UndoAsync(string grid) => StepOpAsync(grid, new { op = "undo" });

    public Task<GridInfo> RedoAsync(string grid) => StepOpAsync(grid, new { op = "redo" });

    /// <summary>Close the table (its dataset and every grid on it).</summary>
    public Task<JsonElement> CloseAsync(string dataset) => _api.DeleteAsync<JsonElement>($"/datasets/{ApiClient.Part(dataset)}");

    /// <summary>A new table from a DuckDB query (the "+" tab's): its grid.</summary>
    public Task<JsonElement> QueryAsync(string name, string sql) =>
        _api.PostAsync<JsonElement>($"/datasets/{ApiClient.Part(name)}/query", new { sql });

    private Task<GridInfo> StepOpAsync(string grid, object body) => _api.PostAsync<GridInfo>($"/grids/{ApiClient.Part(grid)}/step-ops", body);
}
