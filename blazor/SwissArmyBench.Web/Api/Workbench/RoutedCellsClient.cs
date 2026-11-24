using System.Text.Json;

using SwissArmyBench.Web.Api.App;

namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>
/// A cell another kernel runs, by the routes the open project's mode declared (the classic routedCells.ts): its run
/// streamed one output record a line then {done}; a TSX cell's page; a table result opened on the Tables page by its id; the
/// declarations for the editor's TypeScript service, asked once a route. Nothing here names a mode or an extension.
/// </summary>
public sealed class RoutedCellsClient
{
    private readonly ApiClient _api;
    private readonly Dictionary<string, Task<string>> _types = new(StringComparer.Ordinal);

    public RoutedCellsClient(ApiClient api)
    {
        _api = api;
    }

    /// <summary>The run's records as they come (outputs, then one with "done").</summary>
    public IAsyncEnumerable<JsonElement> RunAsync(CellRoute route, RoutedRun run, CancellationToken cancel = default) =>
        _api.PostLinesAsync(route.Run, new { path = run.Path, kind = run.Kind, code = run.Code, cell = run.Cell, stream = true }, cancel);

    /// <summary>A TSX cell drawn: the one page for the design frame.</summary>
    public async Task<string> PreviewAsync(CellRoute route, string? path, string source, int cell)
    {
        if (route.Preview is not { Length: > 0 } preview)
        {
            throw new InvalidOperationException("This cell kind is not drawn here.");
        }
        var drawn = await _api.PostAsync<JsonElement>(preview, new { path, source, cell });
        return drawn.TryGetProperty("html", out var html) ? html.GetString() ?? string.Empty : string.Empty;
    }

    /// <summary>A table result opened on the Tables page by its id: the grid's dataset name.</summary>
    public async Task<string?> OpenTableAsync(CellRoute route, string? path, string id, string? name)
    {
        if (route.Grid is not { Length: > 0 } grid)
        {
            return null;
        }
        var opened = await _api.PostAsync<JsonElement>(grid, new { path, id, name });
        return opened.TryGetProperty("dataset", out var dataset) ? dataset.GetString() : null;
    }

    /// <summary>The route's declarations for the editor (empty when it has none or they cannot be read).</summary>
    public Task<string> TypesAsync(CellRoute route)
    {
        if (route.Types is not { Length: > 0 } url)
        {
            return Task.FromResult(string.Empty);
        }
        if (!_types.TryGetValue(url, out var found))
        {
            found = ReadTypesAsync(url);
            _types[url] = found;
        }
        return found;
    }

    /// <summary>A tool the route needs, installed by its own install route.</summary>
    public Task InstallAsync(CellRoute route, string? tool) =>
        route.Install is { Length: > 0 } install ? _api.PostAsync(install, new { tool }) : Task.CompletedTask;

    private async Task<string> ReadTypesAsync(string url)
    {
        try
        {
            return await _api.GetTextAsync(url);
        }
        catch (ApiException)
        {
            return string.Empty;
        }
    }
}
