using System.Globalization;
using System.Text.Json;

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Grids;
using SwissArmyBench.Web.Api.Relationships;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Grids.Tools;

public partial class KeyFinderDialog
{
    // The first pairs shown; Show all lists the rest.
    private const int First = 25;
    private const int LongestDefault = 128;

    private IReadOnlyList<KeyFinderTarget> _targets = [];
    private string _target = "*";
    private bool _trim = true;
    private bool _ignoreCase;
    private int _maxLength = LongestDefault;
    private KeyFinderResult? _result;
    private Model? _model;
    private bool _running;
    private bool _showAll;
    private string? _open;
    private KeySample? _sample;
    private int _asked;
    private Exception? _error;

    [Inject]
    private GridsClient Grids { get; set; } = default!;

    [Inject]
    private ComparesClient Compares { get; set; } = default!;

    [Inject]
    private RelationshipsClient Relationships { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Parameter, EditorRequired]
    public string Grid { get; set; } = string.Empty;

    [Parameter, EditorRequired]
    public string Dataset { get; set; } = string.Empty;

    /// <summary>Send to Analyze: the result as cards (the page sends them).</summary>
    [Parameter]
    public EventCallback<KeyFinderResult> OnSend { get; set; }

    [Parameter]
    public EventCallback OnClose { get; set; }

    private object Options => new { trim = _trim, ignore_case = _ignoreCase, max_length = Math.Max(1, _maxLength) };

    private string Against => _target == "*" ? "every other open table" : _targets.FirstOrDefault(t => t.Grid == _target)?.Label ?? "the other table";

    private IReadOnlyList<KeyTarget> Targets => _result?.Targets.Select(t => t.Deserialize<KeyTarget>(ApiClient.Json)!).ToList() ?? [];

    private string TargetsWords => Targets.Count > 0 ? string.Join(", ", Targets.Select(t => t.Label)) : "no other table";

    protected override async Task OnInitializedAsync()
    {
        try
        {
            _targets = (await Grids.KeyFinderTargetsAsync(Grid)).Grids;
            _model = await Relationships.ModelAsync();
        }
        catch (ApiException error)
        {
            _error = error;
        }
        // Opened: find them straight away (an empty window only asked to press a button).
        await FindAsync();
    }

    /// <summary>Only the newest search's answer is shown (the one started on opening can come back after another).</summary>
    private async Task FindAsync()
    {
        var mine = ++_asked;
        _running = true;
        try
        {
            var result = await Grids.KeyFinderAsync(Grid, _target, Options);
            if (mine != _asked)
            {
                return;
            }
            _result = result;
            _showAll = false;
            _open = null;
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
        _running = false;
    }

    private IReadOnlyList<KeyPair> Shown(KeyFinderResult result) => _showAll ? result.Pairs : result.Pairs.Take(First).ToList();

    private static string KeyOf(KeyPair pair) => $"{pair.SourceColumn}|{pair.TargetGrid}|{pair.TargetColumn}";

    private async Task ToggleAsync(KeyPair pair)
    {
        var key = KeyOf(pair);
        _open = _open == key ? null : key;
        _sample = null;
        if (_open is null)
        {
            return;
        }
        try
        {
            _sample = await Grids.KeySampleAsync(Grid, pair, Options);
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private Task RowKeyAsync(KeyboardEventArgs e, KeyPair pair) => e.Key == "Enter" ? ToggleAsync(pair) : Task.CompletedTask;

    private async Task CompareOnAsync(KeyPair pair)
    {
        try
        {
            await Compares.StartAsync(Grid, pair.TargetGrid, [[pair.SourceColumn, pair.TargetColumn]], "outer", show: true);
            var on = pair.SourceColumn == pair.TargetColumn ? pair.SourceColumn : $"{pair.SourceColumn} = {pair.TargetColumn}";
            _ = Notes.SayAsync($"{_result?.Source} and {pair.TargetDataset} are side by side on the Tables page, lined up on {on}.");
            await OnClose.InvokeAsync();
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task AddAsync(KeyPair pair)
    {
        var source = _result?.Source ?? Dataset;
        var kind = string.Join("-", pair.Relationship.Split(' ').Take(3));
        var evidence = $"Key Finder: {Percent(pair.SourceFound)} of {source} found, {pair.Shared:N0} shared values";
        try
        {
            await Relationships.AddAsync([new Join(source, [pair.SourceColumn], pair.TargetDataset, [pair.TargetColumn], kind, Evidence: evidence)]);
            _model = await Relationships.ModelAsync();
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private static IReadOnlyList<(SkippedColumn Column, bool Here)> Skipped(KeyFinderResult result)
    {
        if (result.Skipped is not { ValueKind: JsonValueKind.Object } skipped)
        {
            return [];
        }
        return skipped.EnumerateObject()
            .SelectMany(side => side.Value.Deserialize<List<SkippedColumn>>(ApiClient.Json)!.Select(c => (c, side.Name == "source")))
            .OrderByDescending(x => x.Item2)
            .ToList();
    }

    public static string Percent(double share) => $"{(Math.Round(share * 1000) / 10).ToString("0.#", CultureInfo.CurrentCulture)}%";

    private static RenderFragment Bar(double share) => builder =>
    {
        builder.OpenElement(0, "span");
        builder.AddAttribute(1, "class", "kf-bar");
        builder.AddAttribute(2, "aria-hidden", "true");
        builder.OpenElement(3, "span");
        builder.AddAttribute(4, "style", FormattableString.Invariant($"width: {Math.Round(share * 100)}%"));
        builder.CloseElement();
        builder.CloseElement();
    };

    private static RenderFragment Values(IReadOnlyList<JsonElement> values) => builder =>
    {
        if (values.Count == 0)
        {
            builder.OpenElement(0, "span");
            builder.AddAttribute(1, "class", "hint");
            builder.AddContent(2, " none");
            builder.CloseElement();
            return;
        }
        builder.OpenElement(3, "div");
        builder.AddAttribute(4, "class", "kf-values");
        foreach (var value in values)
        {
            builder.OpenElement(5, "code");
            builder.AddContent(6, value.ValueKind == JsonValueKind.String ? value.GetString() : value.GetRawText());
            builder.CloseElement();
        }
        builder.CloseElement();
    };
}
