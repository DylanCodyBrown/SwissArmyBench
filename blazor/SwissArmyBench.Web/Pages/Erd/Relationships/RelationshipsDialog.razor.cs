using System.Text.Json;

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Forms;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Relationships;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Erd.Relationships;

public partial class RelationshipsDialog
{
    // A set's file is small: a larger one is not a relationship set.
    private const long LargestFile = 5_000_000;

    private SetLibrary? _library;
    private Model? _model;
    private RelationshipScope? _scope;
    private IReadOnlyList<RunResult>? _runs;
    private SavedSet? _renaming;
    private bool _saving;
    private (string Name, string Text, ImportReview Review)? _importing;
    private CheckAnswer? _checked;
    private FindRelationships? _finder;
    private Exception? _error;

    [Inject]
    private RelationshipsClient Relationships { get; set; } = default!;

    [Inject]
    private ApiClient Api { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    /// <summary>The grid in front (Draw diagram sends its card there); none: a card of its own.</summary>
    [Parameter]
    public string? Grid { get; set; }

    /// <summary>Run the finder as the window opens (the ERD's Find relationships).</summary>
    [Parameter]
    public bool StartFinding { get; set; }

    [Parameter]
    public EventCallback OnClose { get; set; }

    protected override async Task OnInitializedAsync()
    {
        await GuardAsync(async () => _library = await Relationships.LibraryAsync());
        await ReloadAsync();
    }

    /// <summary>The joins in use and the project's tables again (after any change).</summary>
    private async Task ReloadAsync()
    {
        await GuardAsync(async () =>
        {
            _model = await Relationships.ModelAsync();
            _scope = await Relationships.ScopeAsync();
        });
        StateHasChanged();
    }

    private async Task GuardAsync(Func<Task> work)
    {
        try
        {
            await work();
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private Task ApplyAsync(string name) => GuardAsync(async () =>
    {
        var changed = await Relationships.ApplySetAsync(name);
        Say(changed.Count > 0 ? $"Applied {name}; it changed: {string.Join("; ", changed)}." : $"Applied {name}.", withUndo: true);
        await ReloadAsync();
    });

    private Task CheckSetAsync(string name) => GuardAsync(async () => _checked = await Relationships.CheckAsync(name));

    private Task CheckInUseAsync() => GuardAsync(async () => _runs = (await Relationships.CheckAsync(null)).Results);

    private async Task RenamedAsync(string to)
    {
        _renaming = null;
        _ = Notes.SayAsync($"Renamed to {to}.");
        await GuardAsync(async () => _library = await Relationships.LibraryAsync());
    }

    private Task DeleteSetAsync(SavedSet set) => GuardAsync(async () =>
    {
        await Relationships.DeleteSetAsync(set.Name);
        _ = Notes.SayAsync($"Deleted {set.Name}.");
        _library = await Relationships.LibraryAsync();
    });

    private Task ExportSavedAsync(string name) => Js.InvokeVoidAsync("sab.download", $"/relationships/sets/{ApiClient.Part(name)}").AsTask();

    private Task ExportAsync() => Js.InvokeVoidAsync("sab.download", "/relationships/set").AsTask();

    private async Task SavedAsync(SavedWhere where)
    {
        _saving = false;
        await GuardAsync(async () => _library = await Relationships.LibraryAsync());
        await ReloadAsync();
    }

    /// <summary>Kind or Run changed on some joins, with one Undo.</summary>
    private Task UpdateAsync((IReadOnlyList<Join> Joins, string? Kind, bool? Active, string Words) change) => GuardAsync(async () =>
    {
        var changed = await Relationships.UpdateAsync(change.Joins, change.Kind, change.Active);
        await ReloadAsync();
        if (changed > 0)
        {
            Say($"{change.Words}: {Plural(changed, "relationship")}.", withUndo: true);
        }
    });

    private Task RemoveAsync(IReadOnlyList<Join> joins) => joins.Count == 0 ? Task.CompletedTask : GuardAsync(async () =>
    {
        var removed = await Relationships.RemoveAsync(joins);
        await ReloadAsync();
        Say($"Deleted {Plural(removed, "relationship")}.", withUndo: true);
    });

    private async Task UndoAsync()
    {
        await GuardAsync(Relationships.UndoAsync);
        await ReloadAsync();
        await (_finder?.RefreshKnownAsync() ?? Task.CompletedTask);
        _ = Notes.SayAsync("Undone.");
    }

    private void Say(string words, bool withUndo) =>
        _ = withUndo ? Notes.SayAsync(words, "Undo", () => InvokeAsync(UndoAsync)) : Notes.SayAsync(words);

    private static string Plural(int count, string word) => $"{count} {word}{(count == 1 ? string.Empty : "s")}";

    /// <summary>Import relationships: a model as JSON is merged as it is; a saved set (marked swissarmybench) is
    /// reviewed first.</summary>
    private async Task ImportAsync(InputFileChangeEventArgs e)
    {
        var file = e.File;
        string text;
        using (var reader = new StreamReader(file.OpenReadStream(LargestFile)))
        {
            text = await reader.ReadToEndAsync();
        }
        JsonElement? parsed = null;
        try
        {
            using var document = JsonDocument.Parse(text);
            parsed = document.RootElement.Clone();
        }
        catch (JsonException)
        {
            parsed = null;
        }
        if (parsed is { ValueKind: JsonValueKind.Object } model && !model.TryGetProperty("swissarmybench", out _))
        {
            await GuardAsync(async () =>
            {
                await Relationships.AddModelAsync(model);
                await ReloadAsync();
            });
            return;
        }
        await GuardAsync(async () =>
        {
            var review = await Relationships.ReviewImportAsync(text);
            _library = await Relationships.LibraryAsync();
            _importing = (file.Name, text, review);
        });
    }

    /// <summary>Draw diagram: the joins in use as a diagram card on the Analyze board, then Analyze in front.</summary>
    private Task DrawDiagramAsync() => GuardAsync(async () =>
    {
        var erd = await Relationships.ErdAsync("all");
        var card = new { kind = "diagram", title = "Relationships", body = erd.Mermaid };
        await Api.PostAsync(Grid is null ? "/cards" : $"/grids/{ApiClient.Part(Grid)}/cards", card);
        await OnClose.InvokeAsync();
        _ = Notes.SayAsync("Diagram sent to Analyze.");
        Nav.NavigateTo("analyze");
    });
}
