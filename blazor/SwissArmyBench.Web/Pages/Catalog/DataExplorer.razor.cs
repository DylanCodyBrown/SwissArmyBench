using System.Text.Json;

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Catalog;
using SwissArmyBench.Web.Api.Connections;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Catalog;

public partial class DataExplorer : IDisposable
{
    private const int TypingPauseMilliseconds = 200;
    private const int RecentKept = 6;
    private const int PreviewRows = 20;
    private const string RecentKey = "explorer.recent";

    private static readonly (string Kind, string Label, string Icon)[] _kinds =
    [
        ("connections", "Connections", "plug"), ("tables", "Tables", "table"), ("columns", "Columns", "columns"), ("structures", "Structures", "structures"),
        ("apis", "APIs", "link"), ("variables", "Variables", "settings"), ("blades", "Blades", "blade"),
    ];

    private readonly HashSet<string> _on = [];
    private readonly Dictionary<string, RenderFragment> _previews = [];
    private SearchAnswer? _answer;
    private IReadOnlyList<string> _connections = [];
    private List<string> _recent = [];
    private string _text = string.Empty;
    private string _connection = string.Empty;
    private string _column = string.Empty;
    private string? _selected;
    private int _asked;
    private CancellationTokenSource? _typing;
    private (string Title, IReadOnlyList<MenuEntry> Entries, double X, double Y)? _menu;
    private Exception? _error;

    [Inject]
    private CatalogClient Catalog { get; set; } = default!;

    [Inject]
    private ConnectionsClient Connections { get; set; } = default!;

    [Inject]
    private ApiClient Api { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    /// <summary>The search box's id (two explorers on one page each have their own).</summary>
    [Parameter]
    public string InputId { get; set; } = "explorer-search";

    /// <summary>Something was opened (the Find data dialog closes then).</summary>
    [Parameter]
    public EventCallback OnOpened { get; set; }

    protected override async Task OnInitializedAsync()
    {
        Live.NoticeArrived += OnNotice;
        var kept = await Js.InvokeAsync<string?>("sab.recall", RecentKey);
        _recent = kept is { Length: > 0 } ? kept.Split('\n', StringSplitOptions.RemoveEmptyEntries).ToList() : [];
        try
        {
            var listed = await Catalog.SearchAsync(string.Empty, ["connections"], string.Empty, string.Empty, limit: 200);
            _connections = listed.Groups.SelectMany(g => g.Results.Select(r => r.Name)).ToList();
        }
        catch (ApiException)
        {
            _connections = [];
        }
        await SearchAsync();
    }

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (firstRender)
        {
            await Js.InvokeVoidAsync("sab.focus", $"#{InputId}");
        }
    }

    private async Task SearchAsync()
    {
        var mine = ++_asked;
        try
        {
            await BrowseIfAsync(mine);
            var answer = await Catalog.SearchAsync(_text, _on, _connection, _column);
            if (mine == _asked)
            {
                _answer = answer;
                _error = null;
            }
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task TypedAsync(ChangeEventArgs e)
    {
        _text = e.Value?.ToString() ?? string.Empty;
        _selected = null;
        _typing?.Cancel();
        _typing = new CancellationTokenSource();
        try
        {
            await Task.Delay(TypingPauseMilliseconds, _typing.Token);
        }
        catch (TaskCanceledException)
        {
            return;
        }
        await SearchAsync();
    }

    private async Task KeepRecentAsync()
    {
        var text = _text.Trim();
        if (text.Length == 0)
        {
            return;
        }
        _recent = _recent.Where(t => t != text).Prepend(text).Take(RecentKept).ToList();
        await Js.InvokeVoidAsync("sab.remember", RecentKey, string.Join('\n', _recent));
    }

    private Task RecentAsync(string text)
    {
        _text = text;
        return SearchAsync();
    }

    private Task ChipAsync(string kind)
    {
        if (!_on.Remove(kind))
        {
            _on.Add(kind);
        }
        return SearchAsync();
    }

    private Task ConnectionAsync(ChangeEventArgs e)
    {
        _connection = e.Value?.ToString() ?? string.Empty;
        return SearchAsync();
    }

    private Task EveryResultAsync()
    {
        _column = string.Empty;
        return SearchAsync();
    }

    private static string KindIcon(string kind) => _kinds.FirstOrDefault(k => k.Kind == kind).Icon ?? "data";

    /// <summary>What each kind of result offers (the classic dataExplorer.ts actions).</summary>
    private IReadOnlyList<ExplorerAction> Actions(SearchResult r)
    {
        switch (r.Kind)
        {
            case "connections":
                List<ExplorerAction> connection = [new("Show its tables", "table", () => ShowTablesOfAsync(r.Name))];
                if (r.Loaded == false)
                {
                    connection.Add(new("Load its catalog", "import", () => LoadCatalogAsync(r.Name)));
                }
                connection.Add(new("Copy name", "copy", () => CopyAsync(r.Name, r.Name)));
                return connection;
            case "tables" when r.Source == "shared":
                var sqlName = r.Sql ?? r.Name;
                List<ExplorerAction> shared = r.Setup && r.Connection is { } setUp ? [new("Set up this connection", "plug", () => GoAsync($"connections?name={Uri.EscapeDataString(setUp)}"))] : [];
                shared.Add(new("Copy SQL name", "copy", () => CopyAsync(sqlName, sqlName), sqlName));
                return shared;
            case "tables":
                var sql = r.Source == "grid" ? r.Variable ?? r.Name : r.Sql ?? r.Name;
                var opens = r.Source == "grid" || (r.Connection is not null && r.Place is not null);
                List<ExplorerAction> table = opens ? [new("Open as grid", "rows", () => OpenTableAsync(r)), new("Preview", "eye", () => PreviewAsync(r))] : [];
                table.Add(new(r.Source == "grid" ? "Copy name" : "Copy SQL name", "copy", () => CopyAsync(sql, sql), sql));
                var query = r.Source == "grid" ? r.Variable ?? r.Name : r.Sql;
                if (query is not null)
                {
                    table.Add(new("Query in a notebook", "notebook", () => QueryInNotebookAsync(query)));
                }
                return table;
            case "columns":
                return [new("Copy name", "copy", () => CopyAsync(r.Name, r.Name)), new("Show tables with this column", "link", () => ColumnAsync(r.Name))];
            case "structures":
                var pointer = r.Pointer ?? "$";
                return [new(pointer == "$" ? "Open" : "Open at this node", "structures", () => GoAsync($"structures?id={Uri.EscapeDataString(r.Structure ?? r.File ?? string.Empty)}")), new("Copy path", "copy", () => CopyAsync(pointer, pointer), pointer)];
            case "apis":
                var apiSql = r.Sql ?? r.Name;
                List<ExplorerAction> api = [new("Copy SQL name", "copy", () => CopyAsync(apiSql, apiSql), apiSql)];
                if (r.Sql is { } apiQuery)
                {
                    api.Add(new("Query in a notebook", "notebook", () => QueryInNotebookAsync(apiQuery)));
                }
                return api;
            case "variables":
                return [new("Open in the Environment", "settings", () => GoAsync($"environment?at=settings&name={Uri.EscapeDataString(r.Name)}")), new("Copy name", "copy", () => CopyAsync(r.Name, r.Name))];
            case "blades":
                return [new("Copy its call", "copy", () => CopyAsync(r.Insert?.Python ?? r.Name, "the call"))];
            default:
                return [new("Copy name", "copy", () => CopyAsync(r.Name, r.Name))];
        }
    }

    private async Task RunAsync(SearchResult r, ExplorerAction a)
    {
        _selected = r.Key;
        await a.Run();
    }

    private Task RunFirstAsync(SearchResult r) => Actions(r) is [var first, ..] ? RunAsync(r, first) : Task.CompletedTask;

    private void Menu(SearchResult r, MouseEventArgs e)
    {
        _selected = r.Key;
        _menu = (r.Name, Actions(r).Select(a => new MenuEntry(a.Label, a.Icon, a.Run)).ToList(), e.ClientX, e.ClientY);
    }

    /// <summary>The arrows move through the results, Enter runs the selected one's first action.</summary>
    private async Task KeyAsync(KeyboardEventArgs e)
    {
        var flat = _answer?.Groups.SelectMany(g => g.Results).ToList() ?? [];
        if (flat.Count == 0)
        {
            return;
        }
        var at = flat.FindIndex(r => r.Key == _selected);
        if (e.Key == "ArrowDown")
        {
            _selected = flat[Math.Min(flat.Count - 1, at + 1)].Key;
        }
        else if (e.Key == "ArrowUp")
        {
            _selected = flat[Math.Max(0, at - 1)].Key;
        }
        else if (e.Key == "Enter")
        {
            await KeepRecentAsync();
            await RunFirstAsync(flat[at < 0 ? 0 : at]);
        }
    }

    private async Task CopyAsync(string text, string what)
    {
        if (await Js.InvokeAsync<bool>("sab.copy", text))
        {
            _ = Notes.SayAsync($"Copied {what}");
        }
    }

    private async Task GoAsync(string address)
    {
        await OnOpened.InvokeAsync();
        Nav.NavigateTo(address);
    }

    private async Task ShowTablesOfAsync(string name)
    {
        _connection = name;
        _on.Clear();
        _on.Add("tables");
        _column = string.Empty;
        await SearchAsync();
    }

    private async Task ColumnAsync(string name)
    {
        _column = name;
        _text = string.Empty;
        await SearchAsync();
    }

    private async Task LoadCatalogAsync(string connection)
    {
        try
        {
            await Catalog.LoadCatalogAsync(connection);
            await SearchAsync();
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>An open table's grid, or a connection's table read into a new one.</summary>
    private async Task OpenTableAsync(SearchResult r)
    {
        if (r.Source == "grid" && r.Grid is { } grid)
        {
            await GoAsync($"grids?grid={Uri.EscapeDataString(grid)}");
            return;
        }
        if (r.Connection is { } connection && r.Place is { } place)
        {
            try
            {
                await Connections.OpenAsync(connection, new TreeTable(place.Table, place.Database, place.Schema));
                _ = Notes.SayAsync($"{r.Name} is open as a grid.");
                await OnOpened.InvokeAsync();
            }
            catch (ApiException error)
            {
                _error = error;
            }
        }
    }

    /// <summary>Its first rows under it (a second press folds them away).</summary>
    private async Task PreviewAsync(SearchResult r)
    {
        if (_previews.Remove(r.Key))
        {
            return;
        }
        try
        {
            JsonElement got = r.Source == "grid" && r.Grid is { } grid
                ? await Api.GetAsync<JsonElement>($"/grids/{ApiClient.Part(grid)}/rows?start=0&end={PreviewRows}")
                : await Api.PostAsync<JsonElement>($"/connections/{ApiClient.Part(r.Connection ?? string.Empty)}/preview", r.Place);
            _previews[r.Key] = TablePreview(got);
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private static RenderFragment TablePreview(JsonElement got) => builder =>
    {
        var columns = got.GetProperty("columns").EnumerateArray().Select(c => c.GetString() ?? string.Empty).ToList();
        builder.OpenElement(0, "table");
        builder.AddAttribute(1, "class", "kf-table small");
        builder.OpenElement(2, "thead");
        builder.OpenElement(3, "tr");
        foreach (var column in columns)
        {
            builder.OpenElement(4, "th");
            builder.AddContent(5, column);
            builder.CloseElement();
        }
        builder.CloseElement();
        builder.CloseElement();
        builder.OpenElement(6, "tbody");
        foreach (var row in got.GetProperty("rows").EnumerateArray())
        {
            builder.OpenElement(7, "tr");
            foreach (var cell in row.EnumerateArray())
            {
                builder.OpenElement(8, "td");
                builder.AddContent(9, cell.ValueKind == JsonValueKind.String ? cell.GetString() : cell.ValueKind == JsonValueKind.Null ? string.Empty : cell.GetRawText());
                builder.CloseElement();
            }
            builder.CloseElement();
        }
        builder.CloseElement();
        builder.CloseElement();
    };

    /// <summary>A new notebook cell over the table (the Notebooks page opens with it).</summary>
    private Task QueryInNotebookAsync(string query) => GoAsync($"notebooks?new=1&sql={Uri.EscapeDataString($"SELECT * FROM {query}")}");

    private void OnNotice(Notice notice)
    {
        if (notice.Type is "catalog_loaded" or "catalog_changed" or "grid_shown" or "grid_closed")
        {
            _ = InvokeAsync(async () =>
            {
                await SearchAsync();
                StateHasChanged();
            });
        }
    }

    public void Dispose()
    {
        Live.NoticeArrived -= OnNotice;
        GC.SuppressFinalize(this);
    }
}
