using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Variables;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Layout;

public partial class VariableAnywhere : IAsyncDisposable
{
    // The list is read again when it opens, kept this long so one keystroke's lookups share a read (a variable added
    // in another window shows at once: the classic variableBox.ts FRESH_MS).
    private static readonly TimeSpan _fresh = TimeSpan.FromSeconds(2);

    private IReadOnlyList<OfferedVariable> _offered = [];
    private DateTime _readAt = DateTime.MinValue;
    private string _filter = string.Empty;
    private int _active;
    private BoxPlace? _place;
    private (double X, double Y, bool Selected)? _menu;
    private IJSObjectReference? _module;
    private IJSObjectReference? _watch;
    private DotNetObjectReference<VariableAnywhere>? _self;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Inject]
    private VariablesClient Variables { get; set; } = default!;

    [Inject]
    private VariableAsks Asks { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    private List<OfferedVariable> Shown => _offered
        .Where(v => v.Name.Contains(_filter, StringComparison.OrdinalIgnoreCase))
        .ToList();

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (firstRender)
        {
            _self = DotNetObjectReference.Create(this);
            _module = await Js.InvokeAsync<IJSObjectReference>("import", "./js/textBoxes.js");
            _watch = await _module.InvokeAsync<IJSObjectReference>("install", _self);
        }
    }

    /// <summary>`${` typed in a box: the name typed so far, and where the box is.</summary>
    [JSInvokable("Typed")]
    public async Task TypedAsync(string filter, BoxPlace place)
    {
        if (_place is null || filter != _filter)
        {
            _active = 0;
        }
        _filter = filter;
        await ReadAsync();
        _place = place;
        _active = Math.Min(_active, Shown.Count);
        StateHasChanged();
    }

    [JSInvokable]
    public void Closed()
    {
        _place = null;
        StateHasChanged();
    }

    /// <summary>A key the open list takes from its box: the arrows, Enter, Tab and Escape.</summary>
    [JSInvokable("Key")]
    public async Task KeyAsync(string key)
    {
        var count = Shown.Count + 1;
        switch (key)
        {
            case "ArrowDown":
                _active = (_active + 1) % count;
                break;
            case "ArrowUp":
                _active = (_active + count - 1) % count;
                break;
            case "Enter" or "Tab" when _active < Shown.Count:
                await PutAsync(Shown[_active].Name);
                break;
            case "Enter" or "Tab":
                await NewVariableAsync();
                break;
            default:
                await CloseAsync();
                break;
        }
        StateHasChanged();
    }

    /// <summary>A right-click on a box: the Text menu at the pointer.</summary>
    [JSInvokable]
    public void Menu(double x, double y, bool selected)
    {
        _menu = (x, y, selected);
        StateHasChanged();
    }

    private IReadOnlyList<MenuEntry> MenuEntries(bool selected) =>
    [
        new("Cut", "edit", () => CopyAsync(true), selected ? null : "Nothing selected"),
        new("Copy", "copy", () => CopyAsync(false), selected ? null : "Nothing selected"),
        new("Paste", "import", PasteAsync),
        MenuEntry.Separator,
        new("Insert variable…", "variables", InsertAsync),
    ];

    private async Task CopyAsync(bool cut)
    {
        if (_module is not null && !await _module.InvokeAsync<bool>("copy", cut))
        {
            _ = Notes.SayAsync("The browser did not allow the copy: use Ctrl+C.");
        }
    }

    private async Task PasteAsync()
    {
        if (_module is not null && !await _module.InvokeAsync<bool>("paste"))
        {
            _ = Notes.SayAsync("The browser did not allow the paste: use Ctrl+V.");
        }
    }

    // Insert variable…: the same list, its pick put in at the caret (over the selection).
    private async Task InsertAsync()
    {
        if (_module is null || await _module.InvokeAsync<BoxPlace?>("openAtCaret") is not { } place)
        {
            return;
        }
        _filter = string.Empty;
        _active = 0;
        await ReadAsync();
        _place = place;
        StateHasChanged();
    }

    private async Task PutAsync(string name)
    {
        _place = null;
        if (_module is not null)
        {
            await _module.InvokeVoidAsync("put", name);
        }
    }

    // New variable…: the Add variable form with the typed name; once saved, the name goes in the box as a pick does.
    private async Task NewVariableAsync()
    {
        var typed = _filter.ToUpperInvariant();
        await CloseAsync();
        if (await Asks.AddAsync(typed) is { } added)
        {
            _readAt = DateTime.MinValue;
            await PutAsync(added);
        }
    }

    private async Task CloseAsync()
    {
        _place = null;
        if (_module is not null)
        {
            await _module.InvokeVoidAsync("closed");
        }
    }

    private async Task ReadAsync()
    {
        if (DateTime.UtcNow - _readAt < _fresh)
        {
            return;
        }
        try
        {
            _offered = await Variables.OfferedAsync();
            _readAt = DateTime.UtcNow;
        }
        catch (ApiException)
        {
            // No list from the server: New variable… is still offered.
            _offered = [];
        }
    }

    public async ValueTask DisposeAsync()
    {
        if (_watch is not null)
        {
            await _watch.InvokeVoidAsync("stop");
            await _watch.DisposeAsync();
        }
        if (_module is not null)
        {
            await _module.DisposeAsync();
        }
        _self?.Dispose();
        GC.SuppressFinalize(this);
    }
}
