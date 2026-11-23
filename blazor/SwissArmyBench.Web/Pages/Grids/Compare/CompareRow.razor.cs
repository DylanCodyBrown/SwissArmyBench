using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api.Grids;

namespace SwissArmyBench.Web.Pages.Grids.Compare;

public partial class CompareRow
{
    /// <summary>The compare running on the two grids side by side, or null (no keys yet).</summary>
    [Parameter]
    public GridCompare? Info { get; set; }

    [Parameter, EditorRequired]
    public string LeftName { get; set; } = string.Empty;

    [Parameter, EditorRequired]
    public string RightName { get; set; } = string.Empty;

    /// <summary>Pick keys… or Keys…: the key picker opens.</summary>
    [Parameter]
    public EventCallback OnPickKeys { get; set; }

    /// <summary>A change to the compare (PATCH /compares/{id}): mode, anti_side, or diff options.</summary>
    [Parameter]
    public EventCallback<object> OnChange { get; set; }

    [Parameter]
    public EventCallback OnDiffOptions { get; set; }

    [Parameter]
    public EventCallback OnStop { get; set; }

    private string Caption => Info?.KeyWords ?? "no keys yet";

    private IEnumerable<RibbonTool> Tools
    {
        get
        {
            var cmp = Info;
            string? noKeys = cmp is null ? "Pick keys first." : null;
            yield return new("cmp-keys", cmp is null ? "Pick keys…" : "Keys…", "columns");
            yield return new("cmp-outer", "Outer join", "rows", Disabled: noKeys, Pressed: cmp?.Mode == "outer");
            yield return new("cmp-anti", "Anti join", "exclude", Disabled: noKeys, Pressed: cmp?.Mode == "anti");
            if (cmp?.Mode == "anti")
            {
                yield return new("cmp-side-both", "Both sides", "filter", Pressed: cmp.AntiSide == "both");
                yield return new("cmp-side-left", $"Only in {LeftName}", "filter", Pressed: cmp.AntiSide == "left");
                yield return new("cmp-side-right", $"Only in {RightName}", "filter", Pressed: cmp.AntiSide == "right");
            }
            yield return new("cmp-cross", "Cross compare", "zoom", Disabled: noKeys, Pressed: cmp?.Mode == "cross");
            yield return new("cmp-diff", "Diff", "check", Disabled: noKeys, Pressed: cmp?.Mode == "diff");
            if (cmp?.Mode == "diff")
            {
                var only = cmp.Diff.OnlyDiffering;
                yield return new("cmp-only", "Only differing columns", "columns", only ? "Showing the keys and the columns that differ" : "Showing every column", Pressed: only);
                yield return new("cmp-options", "How values compare…", "settings");
            }
            yield return new("cmp-stop", "Stop compare", "close", Disabled: noKeys);
        }
    }

    /// <summary>Diff options as the server reads them (snake_case through the client's JSON).</summary>
    public static object Options(CompareDiffOptions o) => new
    {
        tolerance = o.Tolerance,
        percent = o.Percent,
        trim = o.Trim,
        ignore_case = o.IgnoreCase,
        skip = o.Skip,
        column = o.Column,
        only_differing = o.OnlyDiffering,
    };

    /// <summary>A changed column's button: only its rows (pressed again, every difference).</summary>
    private Task FocusColumnAsync(GridCompare cmp, string name) =>
        OnChange.InvokeAsync(new { diff = Options(cmp.Diff with { Column = cmp.Diff.Column == name ? null : name }) });

    private Task RunAsync(string tool) => tool switch
    {
        "cmp-keys" => OnPickKeys.InvokeAsync(),
        "cmp-outer" => OnChange.InvokeAsync(new { mode = "outer" }),
        "cmp-anti" => OnChange.InvokeAsync(new { mode = "anti" }),
        "cmp-side-both" => OnChange.InvokeAsync(new { anti_side = "both" }),
        "cmp-side-left" => OnChange.InvokeAsync(new { anti_side = "left" }),
        "cmp-side-right" => OnChange.InvokeAsync(new { anti_side = "right" }),
        "cmp-cross" => OnChange.InvokeAsync(new { mode = "cross" }),
        "cmp-diff" when Info is { } cmp => OnChange.InvokeAsync(new { mode = "diff", diff = Options(cmp.Diff with { Column = null }) }),
        "cmp-only" when Info is { } cmp => OnChange.InvokeAsync(new { diff = Options(cmp.Diff with { OnlyDiffering = !cmp.Diff.OnlyDiffering }) }),
        "cmp-options" => OnDiffOptions.InvokeAsync(),
        "cmp-stop" => OnStop.InvokeAsync(),
        _ => Task.CompletedTask,
    };
}
