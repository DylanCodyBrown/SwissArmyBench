namespace SwissArmyBench.Web.Api.Grids;

/// <summary>Compares (routes_relationships.py's /compares): two grids side by side, lined up row for row on their
/// keys. The rows themselves go from the server into AG Grid directly (GET /compares/{id}/rows).</summary>
public sealed class ComparesClient
{
    private readonly ApiClient _api;

    public ComparesClient(ApiClient api)
    {
        _api = api;
    }

    public async Task<IReadOnlyList<GridCompare>> RunningAsync() => (await _api.GetAsync<ComparesAnswer>("/compares")).Compares;

    public Task<GridCompare> StartAsync(string left, string right, IEnumerable<IReadOnlyList<string>> keys, string mode = "outer") =>
        _api.PostAsync<GridCompare>("/compares", new { left, right, keys, mode });

    public Task<GridCompare> ReadAsync(string compare) => _api.GetAsync<GridCompare>(Base(compare));

    /// <summary>A change of mode, anti join's side or diff mode's options: the compare as it is now.</summary>
    public Task<GridCompare> ChangeAsync(string compare, object patch) => _api.PatchAsync<GridCompare>(Base(compare), patch);

    public Task StopAsync(string compare) => _api.DeleteAsync(Base(compare));

    /// <summary>Aligned compare: the rows sharing the picked row's key, on both grids.</summary>
    public Task<KeyGroup> KeyGroupAsync(string compare, long row) => _api.GetAsync<KeyGroup>($"{Base(compare)}/key-group?row={row}");

    /// <summary>Cross compare: a row picked on one side filters the other side to its key.</summary>
    public Task<GridCompare> FocusAsync(string compare, string side, long position) =>
        _api.PostAsync<GridCompare>($"{Base(compare)}/focus", new { side, position });

    public Task<GridCompare> ClearFocusAsync(string compare) => _api.DeleteAsync<GridCompare>($"{Base(compare)}/focus");

    private static string Base(string compare) => $"/compares/{ApiClient.Part(compare)}";
}
