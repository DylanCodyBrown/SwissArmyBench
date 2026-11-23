using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Grids;
using SwissArmyBench.Web.Api.Projects;

namespace SwissArmyBench.Web.Pages.Grids.Query;

public partial class NewQueryLanding
{
    // Past this many connections, a search box comes first.
    private const int SearchPast = 8;

    private IReadOnlyList<QueryConnection> _connections = [];
    private IReadOnlyList<ProjectProblem> _problems = [];
    private string _search = string.Empty;
    private bool _loaded;
    private Exception? _error;

    [Inject]
    private ApiClient Api { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    /// <summary>Whether a grid is open (Open tables comes first then).</summary>
    [Parameter]
    public bool GridsOpen { get; set; }

    /// <summary>A choice: the draft opens with Query from set ("" the open tables).</summary>
    [Parameter]
    public EventCallback<string> OnChoose { get; set; }

    protected override Task OnInitializedAsync() => LoadAsync();

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (firstRender || (_loaded && _focusPending))
        {
            _focusPending = !_loaded;
            await Js.InvokeVoidAsync("sab.focus", ".new-query-search, .new-query-choice");
        }
    }

    private bool _focusPending = true;

    private async Task LoadAsync()
    {
        try
        {
            _connections = (await Api.GetAsync<ConnectionsListing>("/connections")).Connections.Where(c => c.RunsSql).ToList();
            _problems = (await Api.GetAsync<ProjectAnswer>("/project")).Project?.Problems ?? [];
        }
        catch (ApiException error)
        {
            _error = error;
        }
        _loaded = true;
    }

    private bool Shows(string words) => _search.Trim().Length == 0 || words.Contains(_search.Trim(), StringComparison.CurrentCultureIgnoreCase);

    /// <summary>The arrows move between the choices (and from the search into them); Enter is the button's own.</summary>
    private Task KeyAsync(KeyboardEventArgs e) => e.Key switch
    {
        "ArrowDown" or "ArrowRight" => Js.InvokeVoidAsync("sab.moveFocus", ".new-query-choice", 1).AsTask(),
        "ArrowUp" or "ArrowLeft" => Js.InvokeVoidAsync("sab.moveFocus", ".new-query-choice", -1).AsTask(),
        "Home" => Js.InvokeVoidAsync("sab.focus", ".new-query-choice").AsTask(),
        "End" => Js.InvokeVoidAsync("sab.moveFocus", ".new-query-choice", -1).AsTask(),
        _ => Task.CompletedTask,
    };

    /// <summary>Enter in the search: the first choice shown.</summary>
    private Task SearchKeyAsync(KeyboardEventArgs e)
    {
        if (e.Key != "Enter")
        {
            return Task.CompletedTask;
        }
        var first = _connections.FirstOrDefault(c => Shows($"{c.Name} {c.KindWords}"));
        return GridsOpen && Shows("Open tables (DuckDB)") ? OnChoose.InvokeAsync(string.Empty) : first is null ? Task.CompletedTask : OnChoose.InvokeAsync(first.Name);
    }

    private async Task SampleAsync()
    {
        try
        {
            await Api.PostAsync("/samples/store", new { });
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }
}
