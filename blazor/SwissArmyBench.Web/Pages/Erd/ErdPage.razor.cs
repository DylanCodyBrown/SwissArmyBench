using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Grids;
using SwissArmyBench.Web.Api.Relationships;

namespace SwissArmyBench.Web.Pages.Erd;

public partial class ErdPage
{
    private const string ProjectScope = "project";
    private const string AllScope = "all";

    private string _scope = ProjectScope;
    private ErdAnswer? _erd;
    private string? _erdWords;
    private Model? _model;
    private IReadOnlyList<Suggestion>? _suggestions;
    private Exception? _error;

    [Inject]
    private RelationshipsClient Relationships { get; set; } = default!;

    [Inject]
    private GridsClient Grids { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    protected override async Task OnInitializedAsync()
    {
        await Js.InvokeVoidAsync("sab.setTitle", "ERD");
        await LoadAsync();
    }

    private async Task LoadAsync()
    {
        try
        {
            _model = await Relationships.ModelAsync();
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
        try
        {
            _erd = await Relationships.ErdAsync(_scope);
            _erdWords = _erd.Mermaid.Length == 0 ? "No relationships yet: Find relationships looks among the open tables." : null;
        }
        catch (ApiException error)
        {
            // Nothing to draw is said in words (no relationship among this project's tables), not as an error.
            _erd = null;
            _erdWords = error.Refusal.Error;
        }
    }

    private Task ScopeAsync(string scope)
    {
        _scope = scope;
        return LoadAsync();
    }

    private async Task FindAsync()
    {
        try
        {
            var tables = (await Grids.ListAsync()).Select(g => g.Dataset).Distinct().ToList();
            _suggestions = (await Relationships.FindAsync(tables)).Suggestions;
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private Task AddAsync(Suggestion suggestion) =>
        ChangeAsync(() => Relationships.AddAsync([new Join(suggestion.From, suggestion.FromColumns, suggestion.To, suggestion.ToColumns, suggestion.Kind)]));

    private Task DeleteAsync(Join join) => ChangeAsync(() => Relationships.DeleteAsync([join]));

    private Task UndoAsync() => ChangeAsync(() => Relationships.UndoAsync());

    private async Task ChangeAsync(Func<Task> change)
    {
        try
        {
            await change();
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
        await LoadAsync();
        if (_suggestions is not null)
        {
            await FindAsync();
        }
    }
}
