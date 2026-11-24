using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Grids;

/// <summary>The live notices the Tables page follows (the classic main.ts onLiveNotice): a table opened, closed or
/// renamed elsewhere (the tabs again), a grid changed by the agent or another window (its view again, said), a
/// compare started by the Key Finder or the agent (the two grids side by side).</summary>
public partial class GridsPage
{
    private void OnNotice(Notice notice)
    {
        FollowDiskMark(notice);
        HeardSwap(notice);
        var mine = notice.Text("grid") is { } grid && _infos.ContainsKey(grid);
        if (notice.Type == "grid_shown" && notice.Text("grid") is { } arrived)
        {
            // A push, a file opened, a paste or the agent: the new grid arrives as a tab and comes to the front.
            _ = InvokeAsync(async () =>
            {
                _tabs = await Grids.ListAsync();
                Nav.NavigateTo(Address(arrived, null));
            });
        }
        else if (notice.Type.StartsWith("dataset_", StringComparison.Ordinal) || notice.Type is "grid_closed" or "table_connection")
        {
            var updated = notice.Type == "dataset_updated" && notice.Text("dataset") is { } dataset && _info?.Dataset == dataset;
            _ = InvokeAsync(async () =>
            {
                await LoadAsync();
                StateHasChanged();
                if (updated)
                {
                    _ = Notes.SayAsync($"{notice.Text("dataset")} updated to version {notice.Number("version")}.");
                }
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
                    _ = Notes.SayAsync("The agent changed this table's view.");
                }
                await RecountCompareAsync();
            });
        }
        else if (notice.Type is "file_changed" or "sandbox_changed" or "project_changed")
        {
            _ = InvokeAsync(async () =>
            {
                await LoadMarksAsync();
                StateHasChanged();
            });
        }
        else if (notice.Type == "process_error")
        {
            // A Python session's table that did not arrive (the classic openMenu.ts): said, with its reason.
            var from = notice.Text("label") is { Length: > 0 } label ? label : "Python";
            _ = Notes.SayAsync($"{notice.Text("name") ?? "A table"} did not open from {from}: {notice.Text("message") ?? "no reason given"}");
        }
        else if (notice.Type == "compare_shown" && notice.Text("compare") is { } shown)
        {
            _ = InvokeAsync(() => ShowCompareAsync(shown));
        }
    }
}
