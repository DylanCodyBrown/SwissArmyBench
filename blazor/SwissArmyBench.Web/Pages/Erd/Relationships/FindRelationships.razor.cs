using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Relationships;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Erd.Relationships;

public partial class FindRelationships
{
    // A join this sure (of a hundred) is added at once.
    private const int SureAt = 80;

    private FindAnswer? _found;
    private HashSet<string> _known = [];
    private string? _diagram;
    private bool _finding;

    [Inject]
    private RelationshipsClient Relationships { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Parameter]
    public bool StartFinding { get; set; }

    /// <summary>The joins in use changed (the window reads them again).</summary>
    [Parameter]
    public EventCallback OnChanged { get; set; }

    [Parameter]
    public EventCallback OnUndo { get; set; }

    [Parameter]
    public EventCallback<Exception> OnError { get; set; }

    protected override async Task OnInitializedAsync()
    {
        if (StartFinding)
        {
            await FindAsync();
        }
    }

    /// <summary>The joins found, drawn at once; the confident ones added straight away with one Undo.</summary>
    private async Task FindAsync()
    {
        _finding = true;
        try
        {
            var found = await Relationships.FindAllAsync();
            _found = found;
            _known = found.Suggestions.Where(s => s.Known).Select(s => s.AsJoin.Key).ToHashSet();
            var confident = found.Suggestions.Where(s => !s.Known && s.Confidence >= SureAt / 100.0).Select(s => s.AsJoin).ToList();
            if (confident.Count > 0)
            {
                await Relationships.AddJoinsAsync(confident, found.Keys ?? new Dictionary<string, IReadOnlyList<string>>());
                _known.UnionWith(confident.Select(j => j.Key));
                await OnChanged.InvokeAsync();
                var words = $"Added {confident.Count} join{(confident.Count == 1 ? string.Empty : "s")} found in the data.";
                _ = Notes.SayAsync(words, "Undo", () => InvokeAsync(() => OnUndo.InvokeAsync()));
            }
            await DrawAsync();
        }
        catch (ApiException error)
        {
            await OnError.InvokeAsync(error);
        }
        _finding = false;
    }

    private async Task DrawAsync()
    {
        _diagram = null;
        if (_found is { Suggestions.Count: > 0 } found)
        {
            _diagram = (await Relationships.ErdOfAsync(found.Tables)).Mermaid;
        }
    }

    /// <summary>After an Undo: which found joins are in use now.</summary>
    public async Task RefreshKnownAsync()
    {
        if (_found is null)
        {
            return;
        }
        var now = (await Relationships.ModelAsync()).Relationships.Select(j => j.Key).ToHashSet();
        _known = _found.Suggestions.Select(s => s.AsJoin.Key).Where(now.Contains).ToHashSet();
        await DrawAsync();
        StateHasChanged();
    }

    /// <summary>A row's tick: the join added to the ones in use, or taken out again (each with its Undo).</summary>
    private async Task ToggleAsync(Suggestion s, bool on)
    {
        try
        {
            var join = s.AsJoin;
            if (on)
            {
                await Relationships.AddJoinsAsync([join], _found?.Keys ?? new Dictionary<string, IReadOnlyList<string>>());
                _known.Add(join.Key);
            }
            else
            {
                await Relationships.RemoveAsync([join]);
                _known.Remove(join.Key);
            }
            _ = Notes.SayAsync(on ? $"Added {s.From} → {s.To}." : $"Took out {s.From} → {s.To}.", "Undo", () => InvokeAsync(() => OnUndo.InvokeAsync()));
            await OnChanged.InvokeAsync();
            await DrawAsync();
        }
        catch (ApiException error)
        {
            await OnError.InvokeAsync(error);
        }
    }

    private async Task RejectAsync(Suggestion s)
    {
        try
        {
            await Relationships.RejectAsync(s.AsJoin);
            await FindAsync();
        }
        catch (ApiException error)
        {
            await OnError.InvokeAsync(error);
        }
    }
}
