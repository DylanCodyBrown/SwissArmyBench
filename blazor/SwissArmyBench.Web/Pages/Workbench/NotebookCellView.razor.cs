using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;

using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Pages.Workbench;

public partial class NotebookCellView
{
    private static readonly IReadOnlyList<EditorMenuAction> _lineageMenu = [new("lineage", "Lineage")];

    private CodeEditor? _editor;
    private int _nameKey;
    private string? _typedName;

    /// <summary>The editor's right-click Lineage: this cell back to the data.</summary>
    [Parameter]
    public EventCallback<CellModel> OnLineage { get; set; }

    public CodeEditor? Editor => _editor;

    /// <summary>F1: help on the name at the cursor in this cell's editor.</summary>
    public Task<string?> HelpAsync() => _editor?.HelpAtCursorAsync() ?? Task.FromResult<string?>(null);

    private Task MenuActionAsync(EditorMenuPick pick) => pick.Id == "lineage" ? OnLineage.InvokeAsync(Cell) : Task.CompletedTask;

    /// <summary>The name box: Enter keeps the name, Escape puts the saved one back; either leaves the box.</summary>
    private async Task NameKeyAsync(KeyboardEventArgs e)
    {
        if (e.Key is not ("Enter" or "Escape"))
        {
            return;
        }
        if (e.Key == "Enter" && _typedName is { } typed)
        {
            await NameChangedAsync(new ChangeEventArgs { Value = typed });
        }
        _typedName = null;
        _nameKey++; // the box made again: it shows the name kept and leaves the focus
    }

    [Parameter, EditorRequired]
    public CellModel Cell { get; set; } = default!;

    [Parameter]
    public bool Selected { get; set; }

    /// <summary>The connections a SQL or DAX cell may name.</summary>
    [Parameter]
    public IReadOnlyList<string> Connections { get; set; } = [];

    /// <summary>The editor's context for the server's intelligence (the kernel, the cells around it).</summary>
    [Parameter, EditorRequired]
    public Func<CellModel, IntelContext> IntelFor { get; set; } = default!;

    [Parameter]
    public EventCallback<CellModel> OnRun { get; set; }

    [Parameter]
    public EventCallback<CellModel> OnSelect { get; set; }

    /// <summary>The cell's text or kind changed (the document is unsaved).</summary>
    [Parameter]
    public EventCallback<CellModel> OnChanged { get; set; }

    [Parameter]
    public EventCallback<(CellModel Cell, EditorKey Key)> OnKey { get; set; }

    [Parameter]
    public EventCallback<(CellModel Cell, int By)> OnMove { get; set; }

    [Parameter]
    public EventCallback<CellModel> OnDelete { get; set; }

    /// <summary>More actions: the cell's menu, opened under its button.</summary>
    [Parameter]
    public EventCallback<(CellModel Cell, MouseEventArgs At)> OnMenu { get; set; }

    /// <summary>An error panel's fix, for the notebook to apply.</summary>
    [Parameter]
    public EventCallback<(CellModel Cell, RunErrorFix Fix)> OnFix { get; set; }

    /// <summary>An error panel's frame to go to (In your code, the call stack).</summary>
    [Parameter]
    public EventCallback<(CellModel Cell, RunErrorFrame Frame)> OnGoTo { get; set; }

    /// <summary>The ghost text providers the mode declares.</summary>
    [Parameter]
    public IReadOnlyList<SwissArmyBench.Web.Api.App.InlineProvider> Inline { get; set; } = [];

    /// <summary>The notebook as a provider is told of it, with this cell the one edited.</summary>
    [Parameter]
    public Func<CellModel, object?>? InlineFor { get; set; }

    private Func<object?>? InlineDocument => InlineFor is null || Cell.IsAppCell ? null : () => InlineFor(Cell);

    /// <summary>The notebook's name, for the agent's title.</summary>
    [Parameter]
    public string Document { get; set; } = "the notebook";

    /// <summary>Run up to here: every cell from the top to this one.</summary>
    [Parameter]
    public EventCallback<CellModel> OnRunTo { get; set; }

    // A cell's name is at most this long (the classic MAX_CELL_NAME).
    private const int MaxName = 80;

    [Parameter]
    public EventCallback<(CellModel Cell, string Line)> OnAnswer { get; set; }

    // TypeScript and TSX cells have Monaco's own language service (the route's declarations given to it).
    private Func<IntelContext>? EditorIntel => Cell.IsAppCell || Cell.Kind is "markdown" or "typescript" or "tsx" ? null : () => IntelFor(Cell);

    /// <summary>The cell kinds another kernel runs, as the open project's mode declares them.</summary>
    [Parameter]
    public IReadOnlyDictionary<string, SwissArmyBench.Web.Api.App.CellRoute> Routes { get; set; } = new Dictionary<string, SwissArmyBench.Web.Api.App.CellRoute>();

    /// <summary>A routed table result's Open as grid, by its id.</summary>
    [Parameter]
    public EventCallback<(CellModel Cell, string Id)> OnOpenTable { get; set; }

    /// <summary>The routed kinds the picker offers: the mode's (TypeScript, TSX), and the cell's own.</summary>
    private IEnumerable<(string Kind, string Words)> RoutedKinds =>
        new[] { ("typescript", "TypeScript"), ("tsx", "TSX") }.Where(k => Routes.ContainsKey(k.Item1) || Cell.Kind == k.Item1);

    private string Label => $"Cell {Cell.Number}, {KindWords}";

    private string KindWords => Cell.Kind switch
    {
        "sql" => "SQL",
        "dax" => "DAX",
        "markdown" => "Markdown",
        "html" => "HTML",
        "typescript" => "TypeScript",
        "tsx" => "TSX",
        _ => "Python",
    };

    private string EditorLanguage => Cell.Kind switch
    {
        "code" => "python",
        "sql" => "sql",
        "dax" => "dax",
        "markdown" => "markdown",
        "html" => "html",
        "typescript" => "typescript",
        "tsx" => "tsx",
        _ => "python",
    };

    /// <summary>The Tables group's words for an app cell (its heading, a table's heading, its transformations).</summary>
    private string AppWords => Cell.Role switch
    {
        "tables" => "Tables",
        "table" => $"Table {Cell.Table}",
        "transformations" => $"{Cell.Table}: follows the grid",
        _ => Cell.Role,
    };

    /// <summary>Puts text in at the cursor (a blade's line from the Blades pane).</summary>
    public async Task InsertAsync(string text)
    {
        if (_editor is not null)
        {
            await _editor.InsertAsync(text);
        }
    }

    public async Task RevealLineAsync(int line)
    {
        if (_editor is not null)
        {
            await _editor.RevealLineAsync(line);
        }
    }

    public async Task FocusAsync()
    {
        if (_editor is not null)
        {
            await _editor.FocusAsync();
        }
    }

    private async Task TextChangedAsync(string text)
    {
        Cell.Source = text;
        await OnChanged.InvokeAsync(Cell);
    }

    private async Task KeyAsync(EditorKey key)
    {
        Cell.Source = key.Text;
        if (Cell.Kind is "markdown" or "html" && key.Name is "run" or "runHere")
        {
            Cell.Editing = false; // drawn again: Shift+Enter on Markdown shows it
        }
        await OnKey.InvokeAsync((Cell, key));
    }

    private async Task KindChangedAsync(ChangeEventArgs e)
    {
        Cell.Kind = e.Value?.ToString() ?? "code";
        Cell.Editing = Cell.Kind is "markdown" or "html";
        await OnChanged.InvokeAsync(Cell);
    }

    private async Task NameChangedAsync(ChangeEventArgs e)
    {
        var name = e.Value?.ToString()?.Trim() ?? string.Empty;
        Cell.Name = name.Length == 0 ? null : name;
        await OnChanged.InvokeAsync(Cell);
    }

    private async Task ConnectionChangedAsync(ChangeEventArgs e)
    {
        var name = e.Value?.ToString();
        Cell.Connection = string.IsNullOrEmpty(name) ? null : name;
        await OnChanged.InvokeAsync(Cell);
    }

    private Task EditAsync()
    {
        Cell.Editing = true;
        return OnSelect.InvokeAsync(Cell);
    }

    private Task MarkdownKeyAsync(KeyboardEventArgs e) => e.Key == "Enter" ? EditAsync() : Task.CompletedTask;
}
