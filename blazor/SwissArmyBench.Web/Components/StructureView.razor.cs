using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Structures;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Components;

public partial class StructureView
{
    private bool _text;
    private string? _selected;
    private string? _typed;
    private Exception? _error;

    [Inject]
    private StructuresClient Structures { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Parameter, EditorRequired]
    public StructureDocument Document { get; set; } = default!;

    /// <summary>The structure changed here (its text applied or saved): the page reads it again.</summary>
    [Parameter]
    public EventCallback<StructureDocument> OnChanged { get; set; }

    private async Task CopyPathAsync()
    {
        await Js.InvokeAsync<bool>("sab.copy", _selected ?? StructurePath.Root);
        _ = Notes.SayAsync("Copied the path.");
    }

    /// <summary>The selected node (a list of records) as a table of its own.</summary>
    private Task GridAsync() => DoAsync(async () =>
    {
        var made = await Structures.GridAsync(Document.Id, _selected ?? StructurePath.Root);
        Nav.NavigateTo($"grids?grid={Uri.EscapeDataString(made.Grid ?? string.Empty)}");
    });

    private Task ApplyAsync() => DoAsync(async () =>
    {
        if (_typed is { } text)
        {
            // The answer says how it went (its version, a text error); the value is read again whole.
            await Structures.SetTextAsync(Document.Id, text);
            _typed = null;
            await OnChanged.InvokeAsync(await Structures.GetAsync(Document.Id));
        }
    });

    private Task SaveAsync() => DoAsync(async () =>
    {
        await Structures.SaveAsync(Document.Id, _typed ?? Document.Text, Document.Hash);
        _typed = null;
        _ = Notes.SayAsync($"Saved {Document.Name}.");
        await OnChanged.InvokeAsync(await Structures.GetAsync(Document.Id));
    });

    private async Task DoAsync(Func<Task> action)
    {
        try
        {
            await action();
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }
}
