using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Blades;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench.Blades;

public partial class BladeIde
{
    // The file's stamp is looked at this often for an edit made outside.
    private static readonly TimeSpan _stampEvery = TimeSpan.FromSeconds(2);

    private BladeDetail? _detail;
    private BladeHeader? _header;
    private string _code = string.Empty;
    private string _savedCode = string.Empty;
    private string _stamp = string.Empty;
    private bool _propsDirty;
    private bool _properties;
    private bool _outside;
    private bool _copyOffer;
    private bool _savingAs;
    private CodeEditor? _editor;
    private BladePropertiesPanel? _props;
    private ShownMenu? _menu;
    private Exception? _error;
    private Timer? _watch;

    // The code's size in pixels (8 to 40), 13 its 100%.
    private const int BaseFont = 13;
    private const int SmallestFont = 8;
    private const int LargestFont = 40;
    private int _fontPx = BaseFont;

    [Inject]
    private BladesClient Blades { get; set; } = default!;

    [Inject]
    private Dialogs Dialogs { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Parameter, EditorRequired]
    public string Name { get; set; } = string.Empty;

    /// <summary>Opened just made (New blade): Properties open.</summary>
    [Parameter]
    public bool Fresh { get; set; }

    /// <summary>Unsaved changes or not, for the tab's dot.</summary>
    [Parameter]
    public EventCallback<bool> OnDirty { get; set; }

    /// <summary>Saved under another name (its name changed), or a copy made: the blade to show now.</summary>
    [Parameter]
    public EventCallback<string> OnRenamed { get; set; }

    /// <summary>Close: its tab goes (asked first with unsaved changes).</summary>
    [Parameter]
    public EventCallback OnClose { get; set; }

    /// <summary>Removed: its tab goes.</summary>
    [Parameter]
    public EventCallback OnRemoved { get; set; }

    public bool Dirty => _code != _savedCode || _propsDirty;

    private bool Runnable => _detail is { Kind: not ("snippet" or "secret") };

    private string Language => _detail?.Kind == "snippet" ? (_detail.Language is { Length: > 0 } l ? l : "markdown") : "python";

    private IntelContext IntelFor() => new(null, _detail?.File, null, false, [], [], _detail?.File ?? $"{Name}.py", null);

    private Task<string> CodeNow() => _editor?.TextAsync() ?? Task.FromResult(_code);

    protected override async Task OnInitializedAsync()
    {
        _properties = Fresh;
        await LoadAsync();
        _watch = new Timer(_ => _ = InvokeAsync(LookAtStampAsync), null, _stampEvery, _stampEvery);
    }

    private async Task LoadAsync()
    {
        try
        {
            _detail = await Blades.GetAsync(Name);
            _header = await Blades.HeaderAsync(Name);
            _code = _savedCode = _detail.Kind == "secret" ? string.Join('\n', _detail.EnvNames ?? []) : _detail.Code;
            (_stamp, _propsDirty, _outside) = (_detail.Stamp, false, false);
            _error = null;
            await RelintAsync();
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task ChangedAsync(string text)
    {
        var was = Dirty;
        _code = text;
        if (was != Dirty)
        {
            await OnDirty.InvokeAsync(Dirty);
        }
        await RelintAsync();
    }

    private Task KeyAsync(EditorKey key)
    {
        _code = key.Text;
        return key.Name switch
        {
            "save" => SaveAsync(),
            "saveAs" => SetSavingAs(),
            "runFile" when Runnable => RunAsync(),
            "zoomIn" => ZoomAsync(_fontPx + 1),
            "zoomOut" => ZoomAsync(_fontPx - 1),
            "zoomReset" => ZoomAsync(BaseFont),
            _ => Task.CompletedTask,
        };
    }

    private async Task ZoomAsync(int px)
    {
        _fontPx = Math.Clamp(px, SmallestFont, LargestFont);
        await (_editor?.SetFontSizeAsync(_fontPx) ?? Task.CompletedTask);
        StateHasChanged();
    }

    /// <summary>Close: with unsaved changes it asks (Throw them away, Keep editing).</summary>
    private async Task CloseAsync()
    {
        if (Dirty && !await Dialogs.AskYesNoAsync(Name, $"{Name} has changes that are not saved.", "Throw them away", danger: true, no: "Keep editing"))
        {
            return;
        }
        await OnClose.InvokeAsync();
    }

    private Task SetSavingAs()
    {
        _savingAs = true;
        return Task.CompletedTask;
    }

    /// <summary>Save: the header's changes and the code after the file's header, with the stamp it was read with.</summary>
    public async Task SaveAsync()
    {
        if (_detail is null)
        {
            return;
        }
        _code = await CodeNow();
        var body = new Dictionary<string, object?>(_props?.Changes() ?? new Dictionary<string, object?>()) { ["stamp"] = _stamp };
        if (_detail.Kind != "secret")
        {
            body["code"] = _code;
        }
        try
        {
            var saved = await Blades.SaveAsync(Name, body);
            (_savedCode, _stamp, _propsDirty, _error, _copyOffer) = (_code, saved.Stamp ?? _stamp, false, null, false);
            await Notes.SayAsync($"Saved {saved.Name}.");
            await OnDirty.InvokeAsync(false);
            if (saved.Name != Name)
            {
                await OnRenamed.InvokeAsync(saved.Name);
            }
        }
        catch (ApiException error) when (error.Status == ConflictStatus)
        {
            _outside = true; // changed on disk since it was read: Reload, or Keep mine and Save again
        }
        catch (ApiException error)
        {
            (_error, _copyOffer) = (error, _detail.Pack is not null);
        }
    }

    // The server's answer to a save over a file changed on disk.
    private const int ConflictStatus = 409;

    /// <summary>Cancel: back to the blade as its file has it.</summary>
    private async Task CancelAsync()
    {
        await LoadAsync();
        await OnDirty.InvokeAsync(false);
    }

    private async Task ReloadAsync()
    {
        await LoadAsync();
        await OnDirty.InvokeAsync(false);
    }

    /// <summary>An edit made outside (the stamp looked at every two seconds): taken at once with nothing unsaved,
    /// else the bar asks (Reload, Keep mine).</summary>
    private async Task LookAtStampAsync()
    {
        if (_detail is null || _outside)
        {
            return;
        }
        try
        {
            var now = await Blades.CodeAsync(Name);
            if (now.Stamp == _stamp)
            {
                return;
            }
            if (Dirty)
            {
                (_outside, _stamp) = (true, now.Stamp);
            }
            else
            {
                (_code, _savedCode, _stamp) = (now.Code, now.Code, now.Stamp);
            }
            StateHasChanged();
        }
        catch (ApiException)
        {
            // gone or not readable now: looked at again
        }
    }

    private async Task CopyAsOwnAsync()
    {
        try
        {
            var copied = await Blades.CopyAsync(Name, null, _code == _savedCode ? null : _code);
            await Notes.SayAsync($"Copied as {copied.Name}.");
            await OnRenamed.InvokeAsync(copied.Name);
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task SavedAsAsync(string made)
    {
        _savingAs = false;
        await OnRenamed.InvokeAsync(made);
    }

    private void ShowMenu(MouseEventArgs at)
    {
        var starter = _detail?.Pack is not null;
        List<MenuEntry> entries = starter
            ? [new("Copy as your own", "copy", CopyAsOwnAsync)]
            : [new("Show its file", "folder", () => GuardAsync(() => Blades.ShowAsync(Name)))];
        entries.Add(new("Export", "export", () => Js.InvokeVoidAsync("sab.download", $"/blades/{Uri.EscapeDataString(Name)}/export").AsTask()));
        if (_detail?.Removable == true)
        {
            entries.Add(new("Remove", "trash", RemoveAsync));
        }
        _menu = new ShownMenu("More", entries, at.ClientX, at.ClientY + 4);
    }

    private async Task RemoveAsync()
    {
        if (await Dialogs.AskYesNoAsync($"Remove {Name}?", "Its file and its saved secrets go.", "Remove", danger: true))
        {
            await GuardAsync(async () =>
            {
                await Blades.RemoveAsync(Name);
                await OnRemoved.InvokeAsync();
            });
        }
    }

    private async Task GuardAsync(Func<Task> action)
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

    public void Dispose() => _watch?.Dispose();
}
