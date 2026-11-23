using System.Text.Json;

namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>
/// One cell of a notebook, as the server reads and writes it (domain/notebooks.py Cell.to_json). Its outputs are
/// nbformat's own records, kept as they came so a save writes them back unchanged. Role is the app's part in the
/// Tables group ("tables", "table", "transformations"); empty for a cell of the user's.
/// </summary>
public sealed record NotebookCell
{
    public string Kind { get; init; } = "code";

    public string Source { get; init; } = string.Empty;

    public string? Connection { get; init; }

    public IReadOnlyList<JsonElement> Outputs { get; init; } = [];

    public int? ExecutionCount { get; init; }

    public int? Number { get; init; }

    public string Role { get; init; } = string.Empty;

    public string? Table { get; init; }

    public bool Grouped { get; init; }

    public int? Height { get; init; }

    public string? Name { get; init; }

    /// <summary>The uses line the server says the cell should start with (POST /workbench/tables/arrange).</summary>
    public string? Uses { get; init; }
}
