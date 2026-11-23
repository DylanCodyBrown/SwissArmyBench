using System.Text.Json;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Grids;

namespace SwissArmyBench.Web.Pages.Grids.Swap;

public partial class ConnectionDialog
{
    private readonly Dictionary<SwapSchema, IReadOnlyList<SwapPlace>> _opened = [];
    private TableConnection? _state;
    private SwapPick? _pick;
    private Exception? _error;

    [Inject]
    private GridsClient Grids { get; set; } = default!;

    [Parameter, EditorRequired]
    public string Table { get; set; } = string.Empty;

    /// <summary>The table now reads from another connection (the page says so, with Undo, and offers to point the
    /// code that named the old one at the new).</summary>
    [Parameter]
    public EventCallback<Swapped> OnSwapped { get; set; }

    /// <summary>A query to look over before it runs on the other connection: the connection, the tables, a query to
    /// start from (Write a query…).</summary>
    [Parameter]
    public EventCallback<(string To, IReadOnlyList<string> Tables, string? Sql)> OnReview { get; set; }

    [Parameter]
    public EventCallback OnUndone { get; set; }

    [Parameter]
    public EventCallback OnClose { get; set; }

    protected override async Task OnInitializedAsync()
    {
        try
        {
            _state = await Grids.ConnectionOfAsync(Table);
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private static IReadOnlyList<string> Others(TableConnection state) =>
        state.Others.Where(o => o.ValueKind == JsonValueKind.String).Select(o => o.GetString()!).ToList();

    private async Task SwapAsync(string to, SwapPlace? place)
    {
        try
        {
            var answer = await Grids.SwapConnectionAsync(Table, to, place);
            if (answer.Swapped is { ValueKind: JsonValueKind.Object } swapped)
            {
                await OnClose.InvokeAsync();
                await OnSwapped.InvokeAsync(swapped.Deserialize<Swapped>(ApiClient.Json)!);
            }
            else if (answer.Review is { ValueKind: JsonValueKind.Object })
            {
                await OnClose.InvokeAsync();
                await OnReview.InvokeAsync((to, [Table], null));
            }
            else if (answer.Pick is { ValueKind: JsonValueKind.Object } pick)
            {
                _pick = pick.Deserialize<SwapPick>(ApiClient.Json);
                _opened.Clear();
            }
            else if (answer.Failed is { } failed)
            {
                _error = new ApiException(0, new Refusal(failed), failed);
            }
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task ToggleSchemaAsync(SwapPick pick, SwapSchema schema)
    {
        if (_opened.Remove(schema))
        {
            return;
        }
        try
        {
            _opened[schema] = await Grids.CatalogTablesAsync(pick.To, schema);
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task UndoAsync()
    {
        await OnClose.InvokeAsync();
        await OnUndone.InvokeAsync();
    }
}
