using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api.Catalog;

namespace SwissArmyBench.Web.Pages.Catalog;

/// <summary>The Catalog page's browsing (the classic dataExplorer.ts on the Catalog page): with nothing typed, the tree
/// of every connection and section (CatalogTree) instead of the grouped results; the kinds and the connection still
/// narrow it; the sandbox's order remembered in this browser.</summary>
public partial class DataExplorer
{
    private const string SandboxSortKey = "sandbox.sort";

    private BrowseAnswer? _browsed;
    private string _sandboxSort = "name asc";

    /// <summary>Browse as a tree while nothing is typed (the Catalog page; Find data keeps the list).</summary>
    [Parameter]
    public bool Browse { get; set; }

    private bool Typed => _text.Trim().Length > 0 || _column.Length > 0;

    private bool ShowsTree => Browse && _browsed is not null && (!Typed || _answer is not null);

    // Typed on the Catalog page: the same tree, narrowed to what matches (made once per answer).
    private SearchAnswer? _narrowedFrom;
    private BrowseAnswer? _narrowed;

    private BrowseAnswer TreeAnswer
    {
        get
        {
            if (!Typed || _answer is null)
            {
                return _browsed!;
            }
            if (!ReferenceEquals(_answer, _narrowedFrom))
            {
                _narrowedFrom = _answer;
                _narrowed = CatalogSearchTree.Of(_answer, _browsed);
            }
            return _narrowed!;
        }
    }

    private async Task BrowseIfAsync(int mine)
    {
        // A search's tree needs the connections' states too: the browse is read once and kept while typing.
        if (!Browse || (Typed && _browsed is not null))
        {
            return;
        }
        if (_sandboxSort == "name asc" && await Js.InvokeAsync<string?>("sab.recall", SandboxSortKey) is { Length: > 0 } kept)
        {
            _sandboxSort = kept;
        }
        var (by, order) = _sandboxSort.Split(' ') is [var b, var o] ? (b, o) : ("name", "asc");
        var browsed = await Catalog.BrowseAsync(_on, _connection, by, order);
        if (mine == _asked)
        {
            _browsed = browsed;
        }
    }

    private Task OnlyAsync(string name)
    {
        _connection = name;
        return SearchAsync();
    }

    private async Task SortSandboxAsync(string sort)
    {
        _sandboxSort = sort;
        await Js.InvokeVoidAsync("sab.remember", SandboxSortKey, sort);
        await SearchAsync();
    }
}
