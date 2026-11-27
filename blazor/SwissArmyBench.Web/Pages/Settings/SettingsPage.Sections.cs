using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

namespace SwissArmyBench.Web.Pages.Settings;

/// <summary>The Settings page's section list: which boxes are drawn (one with nothing to show, Updates with no update,
/// is left out), the jump to one, and the mark on the one in view (interop/settings.js tells both).</summary>
public partial class SettingsPage : IAsyncDisposable
{
    private ElementReference _layout;
    private IJSObjectReference? _module;
    private IJSObjectReference? _watch;
    private DotNetObjectReference<SettingsPage>? _self;
    private HashSet<string>? _drawn;
    private string _current = SettingsSection.Theme;
    private Func<string>? _address;

    [Inject]
    private State.PopOuts PopOuts { get; set; } = default!;

    /// <summary>The section to open at (settings?section=agent): a pop-out and its Reattach keep the one in view.</summary>
    [SupplyParameterFromQuery(Name = "section")]
    public string? SectionParameter { get; set; }

    /// <summary>The list's lines: every section until the page says which boxes are drawn, then only those.</summary>
    private IEnumerable<SettingsSection> Listed => SettingsSection.All.Where(s => _drawn?.Contains(s.Id) ?? AlwaysDrawn(s.Id));

    // Before the page has looked: the boxes that come and go are left out, never shown and then taken away.
    private static bool AlwaysDrawn(string id) => id is not (SettingsSection.Project or SettingsSection.Updates);

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (!firstRender)
        {
            return;
        }
        try
        {
            _module = await Js.InvokeAsync<IJSObjectReference>("import", "./js/settings.js");
            _self = DotNetObjectReference.Create(this);
            _watch = await _module.InvokeAsync<IJSObjectReference>("watch", _layout, _self);
            if (SectionParameter is { } wanted && SettingsSection.All.Any(s => s.Id == wanted))
            {
                await JumpAsync(wanted);
                StateHasChanged();
            }
            _address = () => $"settings?section={_current}";
            PopOuts.StateAddress = _address;
        }
        catch (JSException)
        {
            // Without the script the list still names every section; the boxes are all on the page.
        }
    }

    /// <summary>The page's own report: the sections drawn, and the one in view.</summary>
    [JSInvokable]
    public void OnSections(string[] drawn, string current)
    {
        _drawn = [.. drawn];
        var moved = _current != current;
        _current = current;
        if (moved)
        {
            PopOuts.Touch();
        }
        StateHasChanged();
    }

    private async Task JumpAsync(string id)
    {
        _current = id;
        PopOuts.Touch();
        if (_watch is not null)
        {
            await _watch.InvokeVoidAsync("jump", id);
        }
    }

    public async ValueTask DisposeAsync()
    {
        if (ReferenceEquals(PopOuts.StateAddress, _address))
        {
            PopOuts.StateAddress = null;
        }
        try
        {
            if (_watch is not null)
            {
                await _watch.InvokeVoidAsync("dispose");
                await _watch.DisposeAsync();
            }
            if (_module is not null)
            {
                await _module.DisposeAsync();
            }
        }
        catch (JSDisconnectedException)
        {
            // The page is closing: nothing is left to let go of.
        }
        _self?.Dispose();
        GC.SuppressFinalize(this);
    }
}
