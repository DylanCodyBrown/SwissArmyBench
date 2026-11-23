namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>Lineage with values (routes_lineage.py): a notebook's or a script's cell traced back to the data.</summary>
public sealed class LineageClient
{
    private readonly ApiClient _api;

    public LineageClient(ApiClient api)
    {
        _api = api;
    }

    /// <summary>The lineage of a cell: its document (a path, or an unsaved one's title), its number, its cells as
    /// held now (or a script's text), and the kernel its values are read from.</summary>
    public Task<LineageGraph> TraceAsync(string document, int cell, IReadOnlyList<NotebookCell>? cells, string? text, string? kernel) =>
        _api.PostAsync<LineageGraph>("/workbench/lineage", new { document, cell, cells, text, kernel });
}
