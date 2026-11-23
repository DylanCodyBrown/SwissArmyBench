using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Connections;
using SwissArmyBench.Web.Api.Grids;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Grids.Tools;

public partial class ConnectionDialog
{
    private IReadOnlyList<ConnectionCard>? _cards;
    private string _to = string.Empty;
    private string? _words;
    private Exception? _error;

    [Inject]
    private GridsClient Grids { get; set; } = default!;

    [Inject]
    private ConnectionsClient Connections { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Parameter, EditorRequired]
    public string Table { get; set; } = string.Empty;

    [Parameter, EditorRequired]
    public string Grid { get; set; } = string.Empty;

    [Parameter]
    public TableConnection? Current { get; set; }

    /// <summary>The table now reads from another connection (the page reads its grid again).</summary>
    [Parameter]
    public EventCallback OnSwapped { get; set; }

    [Parameter]
    public EventCallback OnClose { get; set; }

    protected override async Task OnInitializedAsync()
    {
        try
        {
            _cards = await Connections.CardsAsync();
            _to = _cards.FirstOrDefault(c => c.Name != Current?.Connection)?.Name ?? string.Empty;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task SwapAsync()
    {
        try
        {
            var answer = await Grids.SwapConnectionAsync(Table, _to);
            if (answer.Swapped is not null)
            {
                _ = Notes.SayAsync($"{Table}: {_to}");
                await OnSwapped.InvokeAsync();
                await OnClose.InvokeAsync();
                return;
            }
            _words = answer.Failed
                ?? (answer.Pick is not null
                    ? $"More than one table in {_to} could be {Table}: pick it in the classic front end."
                    : $"{Table}'s query needs a look before it runs on {_to}: review it in the classic front end.");
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task UndoAsync()
    {
        try
        {
            await Grids.UndoSwapAsync(Table);
            await OnSwapped.InvokeAsync();
            await OnClose.InvokeAsync();
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }
}
