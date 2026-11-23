using System.Text.Json;

using SwissArmyBench.Web.Api.Workbench;

namespace SwissArmyBench.Web.Pages.Workbench;

/// <summary>
/// One cell of the notebook on screen (the classic workbenchNotebook.ts cell): what the file keeps (its kind, text,
/// connection, number, outputs, its part in the Tables group) and what only the page knows (running, the error
/// taken apart, a Markdown cell being edited, the kernel asking for a line).
/// </summary>
public sealed class CellModel
{
    public string Kind { get; set; } = "code";

    public string Source { get; set; } = string.Empty;

    public string? Connection { get; set; }

    public int Number { get; set; }

    public int? ExecutionCount { get; set; }

    public List<JsonElement> Outputs { get; set; } = [];

    /// <summary>The app's part in the Tables group (tables, table, transformations); empty for the user's own.</summary>
    public string Role { get; set; } = string.Empty;

    public string? Table { get; set; }

    public bool Grouped { get; set; }

    public int? Height { get; set; }

    public string? Name { get; set; }

    public bool Running { get; set; }

    /// <summary>Its output folded away (Hide the output); the page's only.</summary>
    public bool OutputHidden { get; set; }

    /// <summary>The last error taken apart by the server (its title, what it means, where).</summary>
    public JsonElement? ErrorDetail { get; set; }

    /// <summary>A Markdown cell shows its text drawn until it is edited.</summary>
    public bool Editing { get; set; }

    /// <summary>The kernel's question while it waits for a line (input(), getpass), with whether it is a password.</summary>
    public (string Prompt, bool Password)? Asking { get; set; }

    /// <summary>A cell of the app's (the Tables group): read-only, it follows the grid.</summary>
    public bool IsAppCell => Role.Length > 0;

    public static CellModel From(NotebookCell cell) => new()
    {
        Kind = cell.Kind,
        Source = cell.Source,
        Connection = cell.Connection,
        Number = cell.Number ?? 0,
        ExecutionCount = cell.ExecutionCount,
        Outputs = [.. cell.Outputs],
        Role = cell.Role,
        Table = cell.Table,
        Grouped = cell.Grouped,
        Height = cell.Height,
        Name = cell.Name,
    };

    public NotebookCell ToSaved() => new()
    {
        Kind = Kind,
        Source = Source,
        Connection = Connection,
        Number = Number,
        ExecutionCount = ExecutionCount,
        Outputs = Outputs,
        Role = Role,
        Table = Table,
        Grouped = Grouped,
        Height = Height,
        Name = Name,
    };
}
