using System.Text.Json;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Grids;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Grids;

/// <summary>
/// A sandbox table's grid (the classic sandboxGrid.ts: sandbox_&lt;table&gt;): its bar (designation, origin, Add row,
/// Delete rows, Reset), its cells edited in place, its tab named by its designation; and a table read from a file
/// that changed on disk (the classic fileChanged.ts: its tab's dot, its pane's Changed on disk with Reload and Not
/// now).
/// </summary>
public partial class GridsPage
{
    private const string SandboxPrefix = "sandbox_";
    private const string AddRow = "add-row";
    private const int MostRowsDeleted = 500;

    private IReadOnlyDictionary<string, SandboxTable> _sandbox = new Dictionary<string, SandboxTable>();
    private (SandboxTable Table, GridPoint At, JsonElement Value)? _editing;
    private HashSet<string> _changedOnDisk = [];
    private bool _diskMarksRead;

    /// <summary>Each sandbox grid's designation ("orders · sandbox"), for its tab.</summary>
    private IReadOnlyDictionary<string, string> Designations => _sandbox.ToDictionary(t => t.Key, t => t.Value.Title);

    private SandboxTable? SandboxOf(string dataset) => _sandbox.GetValueOrDefault(dataset);

    /// <summary>What the sandbox holds, and (once, as the page opens) which files changed on disk: the notices keep
    /// the marks after that (file_changed sets or clears one; a table read again clears its own).</summary>
    private async Task LoadMarksAsync()
    {
        try
        {
            if (!_diskMarksRead)
            {
                _changedOnDisk = (await Api.GetAsync<DatasetsAnswer>("/datasets")).Datasets.Where(d => d.ChangedOnDisk).Select(d => d.Name).ToHashSet();
                _diskMarksRead = true;
            }
            _sandbox = _tabs.Any(t => t.Dataset.StartsWith(SandboxPrefix, StringComparison.Ordinal))
                ? (await Api.GetAsync<SandboxState>("/sandbox")).Tables.ToDictionary(t => $"{SandboxPrefix}{t.Name}")
                : new Dictionary<string, SandboxTable>();
        }
        catch (ApiException)
        {
            // The marks are a convenience: the grids work without them.
        }
    }

    /// <summary>A sandbox grid's cell opens its editor; any other cell its value.</summary>
    private async Task OpenCellAsync(GridPoint at)
    {
        if (_info is { } info && SandboxOf(info.Dataset) is { } table && _grid is not null)
        {
            _editing = (table, at, await _grid.CellAsync(at.Row, at.Column));
            StateHasChanged();
            return;
        }
        await ViewCellAsync(at);
    }

    private async Task DeleteSandboxRowsAsync(SandboxTable table)
    {
        var rows = _grid is null ? [] : await _grid.SelectedRowsAsync(MostRowsDeleted);
        if (rows.Count == 0)
        {
            throw new ApiException(0, new Refusal("Select the rows to delete first (their numbers at the left)."), string.Empty);
        }
        await Api.PostAsync("/sandbox/edit", new { table = table.Name, op = "delete", rows });
    }

    private Task ResetSandboxAsync(SandboxTable table) => Api.PostAsync("/sandbox/reset", new { table = table.Name });

    /// <summary>A notice about a table's file: its mark set or cleared.</summary>
    private void FollowDiskMark(Notice notice)
    {
        if (notice.Text("dataset") is not { } dataset)
        {
            return;
        }
        if (notice.Type == "file_changed" && notice.Flag("changed") == true)
        {
            _changedOnDisk.Add(dataset);
        }
        else if (notice.Type is "file_changed" or "dataset_updated" or "dataset_closed")
        {
            _changedOnDisk.Remove(dataset);
        }
    }

    /// <summary>Reload: the table read again from its file, its grids and their steps kept; Not now leaves it.</summary>
    private async Task ReloadFromDiskAsync(string dataset, bool notNow)
    {
        try
        {
            await Api.PostAsync($"/datasets/{ApiClient.Part(dataset)}/reload", notNow ? new { not_now = true } : new { });
            if (notNow)
            {
                _changedOnDisk.Remove(dataset);
            }
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }
}
