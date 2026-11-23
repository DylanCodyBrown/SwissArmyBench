using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Grids;

/// <summary>The live notices the Grids page follows (the classic main.ts onLiveNotice): a table opened, closed or
/// renamed elsewhere (the tabs again), a grid changed by the agent or another window (its view again, said), a
/// compare started by the Key Finder or the agent (the two grids side by side).</summary>
public partial class GridsPage
{
    private void OnNotice(Notice notice)
    {
        var mine = notice.Text("grid") is { } grid && _infos.ContainsKey(grid);
        if (notice.Type.StartsWith("dataset_", StringComparison.Ordinal) || notice.Type is "grid_closed" or "grid_shown" or "table_connection")
        {
            _ = InvokeAsync(async () =>
            {
                await LoadAsync();
                StateHasChanged();
            });
        }
        else if (notice.Type == "grid_updated" && mine && notice.Text("by") != ApiClient.ClientId)
        {
            _ = InvokeAsync(async () =>
            {
                await ReloadInfoAsync();
                foreach (var (id, pane) in Panes.Where(p => _infos.ContainsKey(p.Key)))
                {
                    await (pane.Grid?.RefreshAsync(_infos[id].Columns) ?? Task.CompletedTask);
                }
                if (notice.Text("by") == "agent")
                {
                    _ = Notes.SayAsync("The agent changed this grid's view.");
                }
                await RecountCompareAsync();
            });
        }
        else if (notice.Type == "compare_shown" && notice.Text("compare") is { } shown)
        {
            _ = InvokeAsync(() => ShowCompareAsync(shown));
        }
    }
}
