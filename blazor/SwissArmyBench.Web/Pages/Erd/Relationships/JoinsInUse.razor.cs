using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;

using SwissArmyBench.Web.Api.Relationships;
using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Pages.Erd.Relationships;

public partial class JoinsInUse
{
    private static readonly string[] _kinds = ["many-to-one", "one-to-one", "one-to-many", "many-to-many"];
    private static readonly (string Key, string Label, string Css)[] _columns =
    [
        ("from", "From", "rel-col-from"), ("to", "To", "rel-col-to"), ("on", "On", "rel-col-on"),
        ("kind", "Kind", "rel-col-kind"), ("run", "Run", "rel-col-run"), ("check", "Check", "rel-col-check"),
    ];

    private static readonly string[] _statusOrder = ["holds", "orphans", "broken", "not open"];

    private readonly HashSet<string> _selected = [];
    private string? _anchor;
    private string _filter = string.Empty;
    private (string Key, bool Down)? _sort;
    private bool _grouped;
    private bool _showAll;
    private bool _checking;
    private (string Title, IReadOnlyList<MenuEntry> Entries, double X, double Y)? _menu;

    [Parameter]
    public Model? Model { get; set; }

    [Parameter]
    public RelationshipScope? Scope { get; set; }

    [Parameter]
    public IReadOnlyList<RunResult>? Runs { get; set; }

    /// <summary>Some joins' kind or Run changed: the joins, the kind, the switch, the words for its Undo note.</summary>
    [Parameter]
    public EventCallback<(IReadOnlyList<Join> Joins, string? Kind, bool? Active, string Words)> OnUpdate { get; set; }

    [Parameter]
    public EventCallback<IReadOnlyList<Join>> OnRemove { get; set; }

    [Parameter]
    public EventCallback OnCheck { get; set; }

    protected override void OnParametersSet()
    {
        // Rows that are gone are no longer selected.
        var now = Model?.Relationships.Select(r => r.Key).ToHashSet() ?? [];
        _selected.IntersectWith(now);
    }

    /// <summary>The rows to draw: the project's (unless All tables), filtered by table or column, sorted, grouped.</summary>
    private IReadOnlyList<Join> Visible(Model model)
    {
        var words = _filter.ToLowerInvariant().Split(' ', StringSplitOptions.RemoveEmptyEntries);
        var used = Scope is { Project: true } scope && !_showAll ? scope.Tables.ToHashSet() : null;
        var rows = model.Relationships
            .Where(r => used is null || (used.Contains(r.From) && used.Contains(r.To)))
            .Where(r => words.All(w => string.Join(' ', new[] { r.From, r.To }.Concat(r.FromColumns).Concat(r.ToColumns)).Contains(w, StringComparison.OrdinalIgnoreCase)));
        IOrderedEnumerable<Join> ordered = _grouped
            ? (_sort is { Key: "from", Down: true } ? rows.OrderByDescending(r => r.From, StringComparer.CurrentCulture) : rows.OrderBy(r => r.From, StringComparer.CurrentCulture))
            : rows.OrderBy(_ => 0);
        if (_sort is { } sort)
        {
            ordered = sort.Down ? ordered.ThenByDescending(r => SortValue(r, sort.Key), StringComparer.CurrentCulture) : ordered.ThenBy(r => SortValue(r, sort.Key), StringComparer.CurrentCulture);
        }
        return ordered.ToList();
    }

    private string SortValue(Join r, string key) => key switch
    {
        "from" => r.From,
        "to" => r.To,
        "on" => r.On,
        "kind" => r.Kind,
        "run" => r.Active ? "0" : "1",
        "check" => (Array.IndexOf(_statusOrder, Run(r)?.Status ?? string.Empty) + 1).ToString(System.Globalization.CultureInfo.InvariantCulture),
        _ => string.Empty,
    };

    /// <summary>Each row, and before the first of each From table a heading (when grouped).</summary>
    private IEnumerable<(Join Join, (string Name, int Count)? Group)> WithGroups(IReadOnlyList<Join> shown) =>
        shown.Select((r, i) => (r, _grouped && (i == 0 || shown[i - 1].From != r.From) ? (r.From, shown.Count(x => x.From == r.From)) : ((string, int)?)null));

    private RunResult? Run(Join r) => Runs?.FirstOrDefault(x => x.Key == r.Key);

    private static (string Icon, string Words) Status(string status) => status switch
    {
        "holds" => ("check", "Holds"),
        "orphans" => ("filter", "Holds, with orphans"),
        "broken" => ("close", "Broken"),
        _ => ("minus", "Not open"),
    };

    private static string NoteOf(Join r, RunResult? ran) => ran is { Status: not "holds" } ? ran.Detail : r.Note ?? string.Empty;

    private string RowClass(Join r, RunResult? ran) => string.Join(' ', new[]
    {
        ran is null ? null : $"run-{ran.Status.Replace(' ', '-')}",
        _selected.Contains(r.Key) ? "selected" : null,
        r.Active ? null : "rel-off",
    }.Where(c => c is not null));

    private string SortWord(string key) => _sort?.Key == key ? (_sort.Value.Down ? "descending" : "ascending") : "none";

    private void SortBy(string key) =>
        _sort = _sort?.Key == key ? (_sort.Value.Down ? null : (key, true)) : (key, false);

    private void SelectAll(IReadOnlyList<Join> shown, bool on)
    {
        foreach (var key in shown.Select(r => r.Key))
        {
            if (on)
            {
                _selected.Add(key);
            }
            else
            {
                _selected.Remove(key);
            }
        }
    }

    /// <summary>A row's tick; with Shift, every row from the last one ticked takes the same state.</summary>
    private void Pick(Join r, IReadOnlyList<Join> shown, bool shift)
    {
        var on = !_selected.Contains(r.Key);
        var keys = shown.Select(x => x.Key).ToList();
        var range = shift && _anchor is not null && keys.Contains(_anchor)
            ? keys.Skip(Math.Min(keys.IndexOf(_anchor), keys.IndexOf(r.Key))).Take(Math.Abs(keys.IndexOf(_anchor) - keys.IndexOf(r.Key)) + 1).ToList()
            : [r.Key];
        foreach (var key in range)
        {
            if (on)
            {
                _selected.Add(key);
            }
            else
            {
                _selected.Remove(key);
            }
        }
        _anchor = r.Key;
    }

    private void RowMenu(Join r, MouseEventArgs e) =>
        _menu = ($"{r.From} → {r.To}",
        [
            new(r.Active ? "Run off" : "Run on", r.Active ? "stop" : "play", () => OnUpdate.InvokeAsync(([r], null, !r.Active, r.Active ? "Run off" : "Run on"))),
            MenuEntry.Separator,
            new("Delete", "trash", () => OnRemove.InvokeAsync([r])),
        ], e.ClientX, e.ClientY);

    private async Task DeletePickedAsync(IReadOnlyList<Join> picked)
    {
        await OnRemove.InvokeAsync(picked);
        _selected.ExceptWith(picked.Select(p => p.Key));
    }

    private static IReadOnlyList<string> Keys(Model model) =>
        (model.Tables ?? new Dictionary<string, ModelTable>())
            .Where(t => t.Value.PrimaryKey is { Count: > 0 })
            .Select(t => $"{t.Key} ({string.Join(", ", t.Value.PrimaryKey!)})")
            .ToList();

    private async Task CheckAsync()
    {
        _checking = true;
        await OnCheck.InvokeAsync();
        _checking = false;
    }
}
