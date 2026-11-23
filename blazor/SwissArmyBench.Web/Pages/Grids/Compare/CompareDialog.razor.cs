using System.Globalization;
using System.Text.Json;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Grids;
using SwissArmyBench.Web.Api.Relationships;

namespace SwissArmyBench.Web.Pages.Grids.Compare;

public partial class CompareDialog
{
    // The best pairs offered (the rest are rarely keys).
    private const int Offered = 20;

    private readonly List<KeyRow> _rows = [];
    private readonly HashSet<string> _ticked = [];
    private string _status = "Finding shared columns…";
    private string _leftPick = string.Empty;
    private string _rightPick = string.Empty;
    private Exception? _error;
    private string? _problem;

    [Inject]
    private GridsClient Grids { get; set; } = default!;

    [Inject]
    private RelationshipsClient Relationships { get; set; } = default!;

    [Parameter, EditorRequired]
    public GridInfo Left { get; set; } = default!;

    [Parameter, EditorRequired]
    public GridInfo Right { get; set; } = default!;

    /// <summary>The compare already running on these two (its keys start ticked), or null.</summary>
    [Parameter]
    public GridCompare? Existing { get; set; }

    /// <summary>Compare: the ticked keys, each [left, right].</summary>
    [Parameter]
    public EventCallback<IReadOnlyList<IReadOnlyList<string>>> OnCompare { get; set; }

    [Parameter]
    public EventCallback OnClose { get; set; }

    protected override async Task OnInitializedAsync()
    {
        _leftPick = Left.Columns.FirstOrDefault()?.Name ?? string.Empty;
        _rightPick = Right.Columns.FirstOrDefault()?.Name ?? string.Empty;
        try
        {
            var finding = Grids.KeyFinderAsync(Left.Grid, Right.Grid);
            var model = await Relationships.ModelAsync();
            var result = await finding;
            Fill(result, model);
        }
        catch (ApiException error)
        {
            _status = string.Empty;
            _error = error;
        }
    }

    private void Fill(KeyFinderResult result, Model model)
    {
        var existing = Existing?.Keys.Select(k => (k[0], k[1])).ToList() ?? [];
        // A known relationship goes first and decides the keys, before any guess.
        var known = existing.Count > 0 ? [] : KnownJoins.Pairs(model, Left.Dataset, Right.Dataset);
        foreach (var (l, r) in known)
        {
            Add(Row(model, l, r, "known relationship"), true);
        }
        var top = result.Pairs.Take(Offered).ToList();
        _status = top.Count > 0
            ? $"{result.PairCount.ToString("N0", CultureInfo.CurrentCulture)} column pair{(result.PairCount == 1 ? string.Empty : "s")} share values."
            : "No shared values.";
        var suggested = SuggestedKey(result);
        foreach (var pair in top)
        {
            var key = (pair.SourceColumn, pair.TargetColumn);
            var ticked = existing.Count > 0 ? existing.Contains(key) : known.Count == 0 && key == suggested;
            Add(new KeyRow(pair.SourceColumn, pair.TargetColumn, Percent(pair.SourceFound), Percent(pair.TargetFound), pair.Shared.ToString("N0", CultureInfo.CurrentCulture), pair.Relationship, IsKnown(model, pair.SourceColumn, pair.TargetColumn)), ticked);
        }
        // The suggested key is usually among the best twenty; when it is not, it is still offered, ticked.
        if (existing.Count == 0 && known.Count == 0 && suggested is { } best && !_rows.Any(r => (r.Left, r.Right) == best))
        {
            Add(Row(model, best.Left, best.Right, "unique on both sides"), true);
        }
        foreach (var (l, r) in existing.Where(k => !top.Any(p => (p.SourceColumn, p.TargetColumn) == k)))
        {
            Add(Row(model, l, r, "current key"), true);
        }
    }

    private static (string Left, string Right)? SuggestedKey(KeyFinderResult result) =>
        result.SuggestedKey is { ValueKind: JsonValueKind.Array } key && key.GetArrayLength() == 2
            ? (key[0].GetString() ?? string.Empty, key[1].GetString() ?? string.Empty)
            : null;

    private KeyRow Row(Model model, string left, string right, string why) =>
        new(left, right, string.Empty, string.Empty, string.Empty, why, IsKnown(model, left, right));

    private bool IsKnown(Model model, string left, string right) => KnownJoins.IsKnown(model, Left.Dataset, Right.Dataset, left, right);

    private static string Percent(double share) => $"{(Math.Round(share * 1000) / 10).ToString("0.#", CultureInfo.CurrentCulture)}%";

    /// <summary>A row, ticked or not; a pair already listed is ticked instead of listed twice.</summary>
    private void Add(KeyRow row, bool ticked)
    {
        if (!_rows.Any(r => r.Id == row.Id))
        {
            _rows.Add(row);
        }
        if (ticked)
        {
            _ticked.Add(row.Id);
        }
    }

    private void Tick(KeyRow row, bool on)
    {
        if (on)
        {
            _ticked.Add(row.Id);
        }
        else
        {
            _ticked.Remove(row.Id);
        }
    }

    private void AddPair()
    {
        if (_leftPick.Length > 0 && _rightPick.Length > 0)
        {
            Add(new KeyRow(_leftPick, _rightPick, string.Empty, string.Empty, string.Empty, "added by hand", false), true);
        }
    }

    private async Task GoAsync()
    {
        var keys = _rows.Where(r => _ticked.Contains(r.Id)).ToList();
        if (keys.Select(k => k.Left).Distinct().Count() < keys.Count || keys.Select(k => k.Right).Distinct().Count() < keys.Count)
        {
            _problem = "Use each column in one key pair only.";
            return;
        }
        await OnCompare.InvokeAsync(keys.Select(k => (IReadOnlyList<string>)[k.Left, k.Right]).ToList());
    }
}
