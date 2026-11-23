using System.Globalization;

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Catalog;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Catalog;

/// <summary>The Catalog's tree (the classic dataBrowse.ts): its nodes from the browse answer, what is open (kept
/// across answers), the selected node and its detail, a connection's table's columns read when it opens, the keys,
/// the sandbox's sort, a dataset's relationships imported.</summary>
public partial class CatalogTree
{
    private const int LongCopy = 60;

    private static readonly (string Key, string Words)[] _sandboxSorts =
        [("name", "Name"), ("rows", "Rows"), ("source", "Source"), ("created", "Created"), ("changed", "Last changed")];

    private readonly HashSet<string> _opened = [];
    private readonly Dictionary<string, Task<TableDetail>> _details = [];
    private BrowseAnswer? _built;
    private List<TreeNode> _roots = [];
    private TreeNode? _detailOf;
    private TableDetail? _detail;
    private Exception? _detailError;
    private Exception? _error;
    private bool _importing;
    private (string Title, IReadOnlyList<MenuEntry> Entries, double X, double Y)? _menu;

    [Inject]
    private CatalogClient Catalog { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Parameter, EditorRequired]
    public BrowseAnswer Answer { get; set; } = default!;

    /// <summary>A result's actions: the Data Explorer's own (Open as grid, Preview, Copy SQL name…).</summary>
    [Parameter, EditorRequired]
    public Func<SearchResult, IReadOnlyList<ExplorerAction>> Actions { get; set; } = default!;

    /// <summary>The previews the Explorer's Preview drew, by the result's key.</summary>
    [Parameter]
    public IReadOnlyDictionary<string, RenderFragment> Previews { get; set; } = new Dictionary<string, RenderFragment>();

    /// <summary>The sandbox's order, "name asc" and the like.</summary>
    [Parameter]
    public string SandboxSort { get; set; } = "name asc";

    /// <summary>A typed search's narrowed tree: everything open, "Nothing matches" when empty.</summary>
    [Parameter]
    public bool Searching { get; set; }

    [Parameter]
    public EventCallback<string> OnOnly { get; set; }

    [Parameter]
    public EventCallback<string> OnLoad { get; set; }

    [Parameter]
    public EventCallback<string> OnSort { get; set; }

    public IReadOnlySet<string> Opened => _opened;

    public string? Selected { get; private set; }

    public HashSet<string> Loading { get; } = [];

    public Dictionary<string, string> Failed { get; } = [];

    protected override void OnParametersSet()
    {
        if (!ReferenceEquals(Answer, _built))
        {
            _built = Answer;
            _roots = CatalogTreeNodes.Of(Answer, Searching);
        }
    }

    /// <summary>What a line offers: a result's actions; a connection's Load, Show only this and Copy name; the
    /// sandbox's Sort; a dataset's or schema's Import its relationships.</summary>
    public IReadOnlyList<ExplorerAction> ActionsOf(TreeNode node)
    {
        if (node.Result is { } r && node.Kind is "table" or "item" or "column")
        {
            return Actions(r);
        }
        var c = node.Connection;
        List<ExplorerAction> own = [];
        if (node.Kind == "connection" && c is not null)
        {
            if (!c.Loaded && c.State.State is not ("loading" or "waiting"))
            {
                own.Add(new("Load", "import", () => OnLoad.InvokeAsync(c.Name), $"Load {c.Name}'s tables"));
            }
            own.Add(new("Show only this", "filter", () => OnOnly.InvokeAsync(c.Name)));
            own.Add(new("Copy name", "copy", () => CopyAsync(c.Name)));
        }
        if (node is { Kind: "section", Key: "section/sandbox" })
        {
            own.Add(new("Sort", "sortup", SortMenu, "Sort the sandbox's tables"));
        }
        if (node is { Kind: "group", Group: { } g } && c is { Relationships: true })
        {
            own.Add(new("Import its relationships", "diagram", () => ImportAsync(c.Name, g.Schema)));
        }
        return own;
    }

    public async Task ClickAsync(TreeNode node)
    {
        await SelectAsync(node);
        if (node.Children is not null && node.Kind != "table")
        {
            await ToggleAsync(node);
        }
        StateHasChanged();
    }

    public async Task RunAsync(TreeNode node, ExplorerAction action)
    {
        await SelectAsync(node);
        StateHasChanged();
        await action.Run();
        StateHasChanged();
    }

    public async Task RunFirstAsync(TreeNode node)
    {
        if (ActionsOf(node) is [var first, ..])
        {
            await first.Run();
            StateHasChanged();
        }
    }

    public void Menu(TreeNode node, MouseEventArgs e)
    {
        var own = ActionsOf(node);
        if (own.Count == 0)
        {
            return;
        }
        Selected = node.Key;
        _menu = (node.Label, [.. own.Select(a => new MenuEntry(a.Label, a.Icon, a.Run))], e.ClientX, e.ClientY);
        StateHasChanged();
    }

    /// <summary>A node opened or closed (to: the state wanted); a connection's table reads its columns the first
    /// time it opens.</summary>
    public async Task ToggleAsync(TreeNode node, bool? to = null)
    {
        if (node.Children is null)
        {
            return;
        }
        var now = node.IsOpen(_opened);
        var next = to ?? !now;
        if (next == now)
        {
            return;
        }
        _opened.Remove(next ? $"!{node.Key}" : node.Key);
        _opened.Add(next ? node.Key : $"!{node.Key}");
        StateHasChanged();
        if (next && node is { Lazy: true, Children.Count: 0, Result: { } r })
        {
            Loading.Add(node.Key);
            Failed.Remove(node.Key);
            try
            {
                var d = await DetailAsync(r);
                node.Children = [.. d.Columns.Select(c => CatalogTreeNodes.Column(node.Key, c))];
                node.Lazy = node.Children.Count == 0;
            }
            catch (ApiException error)
            {
                Failed[node.Key] = error.Message;
            }
            Loading.Remove(node.Key);
            StateHasChanged();
        }
    }

    private async Task SelectAsync(TreeNode node)
    {
        Selected = node.Key;
        if (node is not { Kind: "table", Result: { } r } || ReferenceEquals(_detailOf, node))
        {
            return;
        }
        _detailOf = node;
        _detail = null;
        _detailError = null;
        if (r.Source != "catalog")
        {
            return;
        }
        try
        {
            var d = await DetailAsync(r);
            if (ReferenceEquals(_detailOf, node))
            {
                _detail = d;
            }
        }
        catch (ApiException error)
        {
            _detailError = error;
        }
    }

    /// <summary>A connection's table's detail, read once (a failure is read again next time).</summary>
    private Task<TableDetail> DetailAsync(SearchResult r)
    {
        var place = r.Place ?? new TablePlace(r.Name);
        var key = string.Join('\u0000', r.Connection, place.Database, place.Schema, place.Table);
        if (!_details.TryGetValue(key, out var found) || found.IsFaulted)
        {
            found = Catalog.TableAsync(r.Connection ?? string.Empty, place);
            _details[key] = found;
        }
        return found;
    }

    private Task SortMenu()
    {
        var (by, order) = SandboxSort.Split(' ') is [var b, var o] ? (b, o) : ("name", "asc");
        _menu = ("Sort the sandbox's tables", [.. _sandboxSorts.Select(s => new MenuEntry(
            s.Words,
            s.Key == by ? (order == "desc" ? "sortdown" : "sortup") : "rows",
            () => OnSort.InvokeAsync($"{s.Key} {(s.Key == by && order == "asc" ? "desc" : "asc")}")))], 240, 160);
        return Task.CompletedTask;
    }

    private async Task ImportAsync(string connection, string dataset)
    {
        var what = dataset.Length > 0 ? dataset : connection;
        _importing = true;
        _ = Notes.SayAsync($"Reading {what}'s relationships…");
        try
        {
            var got = await Catalog.ImportRelationshipsAsync(connection, dataset);
            _ = Notes.SayAsync($"{got.Imported.Count.ToString(CultureInfo.InvariantCulture)} relationships from {what} are in the model.");
        }
        catch (ApiException error)
        {
            _error = error;
        }
        _importing = false;
    }

    private async Task CopyAsync(string text)
    {
        if (await Js.InvokeAsync<bool>("sab.copy", text))
        {
            _ = Notes.SayAsync($"Copied {(text.Length > LongCopy ? "the code" : text)}");
        }
    }

    /// <summary>The lines shown, in order (an open node's children after it).</summary>
    private List<TreeNode> Visible()
    {
        var shown = new List<TreeNode>();
        void Walk(IEnumerable<TreeNode> nodes)
        {
            foreach (var n in nodes)
            {
                shown.Add(n);
                if (n.IsOpen(_opened))
                {
                    Walk(n.Children!);
                }
            }
        }
        Walk(_roots);
        return shown;
    }

    private TreeNode? ParentOf(TreeNode child) =>
        Visible().LastOrDefault(n => n.Children?.Contains(child) == true);
}
