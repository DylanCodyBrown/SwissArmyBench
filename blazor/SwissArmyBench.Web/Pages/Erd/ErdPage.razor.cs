using System.Text.Json;

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Forms;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Grids;
using SwissArmyBench.Web.Api.Relationships;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Erd;

public partial class ErdPage
{
    private const long LargestFile = 5_000_000;

    private ErdAnswer? _erd;
    private Model? _model;
    private RelationshipScope? _scope;
    private IReadOnlyList<string> _covered = [];
    private IReadOnlyList<SavedSet> _shared = [];
    private bool _showAll;
    private bool _fitted = true;
    private bool _noneHere;
    private bool? _window;
    private Exception? _error;

    [Inject]
    private RelationshipsClient Relationships { get; set; } = default!;

    [Inject]
    private GridsClient Grids { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    /// <summary>No relationship covers a table to draw (and no project hides them): the empty state.</summary>
    private bool Empty => _covered.Count == 0 && !_noneHere;

    protected override async Task OnInitializedAsync()
    {
        Live.NoticeArrived += OnNotice;
        await Js.InvokeVoidAsync("sab.setTitle", "ERD");
        await LoadAsync();
    }

    /// <summary>Which tables to draw (the classic render): a project's (or all of them); with none open the open
    /// tables, else the whole model.</summary>
    private async Task LoadAsync()
    {
        try
        {
            _model = await Relationships.ModelAsync();
            var open = (await Grids.ListAsync()).Select(g => g.Dataset).ToHashSet();
            var named = (_model.Tables?.Keys ?? []).Concat(_model.Relationships.SelectMany(r => new[] { r.From, r.To })).Distinct().ToList();
            var openPart = named.Where(open.Contains).ToList();
            _scope = named.Count > 0 ? await Relationships.ScopeAsync() : null;
            var inProject = _scope?.Project == true;
            _covered = inProject ? (_showAll ? named : _scope!.Tables) : openPart.Count > 0 || _model.Relationships.Count == 0 ? openPart : named;
            _noneHere = _covered.Count == 0 && inProject && named.Count > 0;
            _erd = _covered.Count == 0 ? null : inProject && _showAll ? await Relationships.ErdAsync("all") : await Relationships.ErdOfAsync(_covered);
            _shared = _covered.Count == 0 && !_noneHere
                ? (await Relationships.LibraryAsync()).Models.Where(m => m.OpenTables.Any(open.Contains)).ToList()
                : [];
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task ScopeAsync(bool all)
    {
        _showAll = all;
        await LoadAsync();
    }

    private void OpenWindow(bool finding) => _window = finding;

    private async Task WindowClosedAsync()
    {
        _window = null;
        await LoadAsync();
    }

    private async Task ApplySharedAsync(string name)
    {
        try
        {
            await Relationships.ApplySetAsync(name);
            _ = Notes.SayAsync($"Applied {name}.");
            await LoadAsync();
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>Import relationships: a model as JSON merged as it is; a saved set opens the window to review it.</summary>
    private async Task ImportAsync(InputFileChangeEventArgs e)
    {
        string text;
        using (var reader = new StreamReader(e.File.OpenReadStream(LargestFile)))
        {
            text = await reader.ReadToEndAsync();
        }
        try
        {
            using var document = JsonDocument.Parse(text);
            var root = document.RootElement;
            if (root.ValueKind == JsonValueKind.Object && !root.TryGetProperty("swissarmybench", out _))
            {
                await Relationships.AddModelAsync(root.Clone());
            }
            else
            {
                var review = await Relationships.ReviewImportAsync(text);
                await Relationships.ApplyImportAsync(text, save: false, folder: null);
                _ = Notes.SayAsync($"Applied {review.Set.Name}.");
            }
            await LoadAsync();
        }
        catch (JsonException)
        {
            _ = Notes.SayAsync($"Could not import {e.File.Name}: it is not JSON.");
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private void OnNotice(Notice notice)
    {
        // relationship_sets_changed: a saved set was added, renamed or removed (the shared models offered here).
        if (notice.Type is "relationships_updated" or "relationship_sets_changed" or "grid_shown" or "grid_closed" or "project_changed")
        {
            _ = InvokeAsync(async () =>
            {
                await LoadAsync();
                StateHasChanged();
            });
        }
    }

    public void Dispose()
    {
        Live.NoticeArrived -= OnNotice;
        GC.SuppressFinalize(this);
    }
}
