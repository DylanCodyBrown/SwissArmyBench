using Microsoft.JSInterop;

using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.Pages.Grids.Tabs;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Grids;

/// <summary>
/// The grid page's commands for the palette (the classic gridCommands.ts): the ribbon's rows by their names, the
/// steps, the cell in front, the tabs (Compare with…, Rename, Close, Go to, Next and Previous tab, Reopen the last
/// closed tab), Find data… (Ctrl+K).
/// </summary>
public partial class GridsPage
{
    [Microsoft.AspNetCore.Components.Inject]
    private Commands Palette { get; set; } = default!;

    [Microsoft.AspNetCore.Components.Inject]
    private Api.Analyze.AnalyzeClient AnalyzeApi { get; set; } = default!;

    // The Analyze page's analyses, from its own toolbar data (8.3: one list feeds the toolbar, the palette, the
    // agent), read once as the page opens.
    private IReadOnlyList<Api.Analyze.AnalysisEntry> _analyses = [];

    private void OfferCommands()
    {
        Palette.FindData = true;
        Palette.SetPageCommands(PageCommands);
        Palette.Changed += PaletteChanged;
        _ = ReadAnalysesAsync();
    }

    private async Task ReadAnalysesAsync()
    {
        try
        {
            _analyses = (await AnalyzeApi.ToolbarAsync(null)).Analyses;
        }
        catch (Api.ApiException)
        {
            // No Analyze entries in the palette: the rest of it stands.
            _analyses = [];
        }
    }

    private void WithdrawCommands()
    {
        Palette.FindData = false;
        Palette.SetPageCommands(null);
        Palette.Changed -= PaletteChanged;
    }

    private void PaletteChanged() => InvokeAsync(StateHasChanged);

    private IReadOnlyList<PaletteCommand> PageCommands()
    {
        var all = new List<PaletteCommand>();
        if (_info is { } info)
        {
            all.AddRange(RibbonTools.Table(info, ConnectionLabel).Select(t => Tool("Table", t)));
            all.AddRange(RibbonTools.Column(info, Target).Select(t => Tool("Column", t)));
            all.Add(new("steps.undo", "Steps", "Undo", UndoAsync, "Ctrl+Z", info.CanUndo ? null : "Nothing to undo"));
            all.Add(new("steps.redo", "Steps", "Redo", RedoAsync, "Ctrl+Y", info.CanRedo ? null : "Nothing to redo"));
            all.Add(new("steps.clear-the-steps", "Steps", "Clear the steps", ClearStepsAsync, WhyNot: info.Steps.Count > 0 ? null : "nothing to act on"));
            all.Add(new("steps.view-steps", "Steps", "View steps", OpenStepsWindowAsync));
            var cell = SelectedCell;
            all.AddRange(CellEntries(cell ?? new GridPoint(0, string.Empty, 0, 0))
                .Where(e => e != MenuEntry.Separator)
                .Select(e => new PaletteCommand($"cell.{Slug(e.Label)}", "Cell", e.Label, e.Run, WhyNot: cell is null ? "Click a cell first" : e.Disabled)));
            var many = _tabs.Count > 1;
            all.Add(new("tabs.compare-with", "Tabs", $"Compare {info.Dataset} with…", () => CompareWithAsync(info.Grid, 0, 0), WhyNot: many ? null : "Open another table to compare with"));
            all.Add(new("tabs.rename", "Tabs", $"Rename {info.Dataset}", () => _tabRow?.StartRenameAsync(info.Grid) ?? Task.CompletedTask, "F2"));
            all.Add(new("tabs.close", "Tabs", $"Close {info.Dataset}", () => CloseGridAsync(info.Grid), "Delete"));
        }
        all.AddRange(_tabs.Select(t => new PaletteCommand($"tabs.go.{t.Grid}", "Tabs", $"Go to {TabOrder.Label(t, _tabs, _order)}", () => ActivateAsync(t.Grid))));
        all.Add(new("tabs.analyze", "Tabs", "Go to Analyze", () => Navigate("analyze")));
        all.Add(new("tabs.erd", "Tabs", "Go to ERD", () => Navigate("erd")));
        all.Add(new("tabs.workbench", "Tabs", "Open the Workbench", () => Navigate("notebooks")));
        all.Add(new("tabs.closeTab", "Tabs", "Close the tab", () => _active is { } a ? CloseGridAsync(a) : Task.CompletedTask, WhyNot: _tabs.Count > 0 ? null : "no tab is open"));
        all.Add(new("tabs.next", "Tabs", "Next tab", () => CycleAsync(1), WhyNot: _tabs.Count > 1 ? null : "one table or none is open"));
        all.Add(new("tabs.previous", "Tabs", "Previous tab", () => CycleAsync(-1), WhyNot: _tabs.Count > 1 ? null : "one table or none is open"));
        all.Add(new("tabs.reopen", "Tabs", "Reopen the last closed tab", ReopenAsync));
        all.Add(new("tabs.new-query", "Tabs", "New query", () => Navigate("grids?new=1")));
        all.Add(new("application.zoom-reset", "Application", "Zoom 100%", () => Js.InvokeVoidAsync("sab.zoomReset").AsTask(), "Ctrl+0"));
        all.Add(new("application.find-data", "Application", "Find data…", () => { Palette.Show("find"); return Task.CompletedTask; }, "Ctrl+K"));
        all.AddRange(_analyses.Select(a => new PaletteCommand(
            $"analyze.{Slug($"{a.Label} ({a.Name})")}",
            "Analyze",
            $"{a.Label} ({a.Name})",
            () => Navigate(_active is { } grid ? $"analyze?analysis={Uri.EscapeDataString(a.Id)}&table={Uri.EscapeDataString(grid)}" : $"analyze?analysis={Uri.EscapeDataString(a.Id)}"))));
        return all;
    }

    private static string Slug(string words) =>
        string.Join('-', new string([.. words.ToLowerInvariant().Select(c => char.IsLetterOrDigit(c) ? c : ' ')])
            .Split(' ', StringSplitOptions.RemoveEmptyEntries));

    private PaletteCommand Tool(string group, RibbonTool tool) =>
        new($"{group.ToLowerInvariant()}.{tool.Id}", group, tool.Pressed ? $"{tool.Label} (on)" : tool.Label, () => RunToolAsync(tool.Id), WhyNot: tool.Disabled);

    private Task Navigate(string address)
    {
        Nav.NavigateTo(address);
        return Task.CompletedTask;
    }

    /// <summary>Next or previous table, round the tab row.</summary>
    private Task CycleAsync(int by)
    {
        if (_order.Count == 0)
        {
            return Task.CompletedTask;
        }
        var at = Math.Max(0, _order.ToList().IndexOf(_active ?? string.Empty));
        return ActivateAsync(_order[(at + by + _order.Count) % _order.Count]);
    }
}
