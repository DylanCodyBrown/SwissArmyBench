using System.Text.Json;

using Microsoft.JSInterop;

namespace SwissArmyBench.Web.Components;

/// <summary>
/// One page's dock (PaneDock): the layout in use, told by Changed, remembered in this browser under its key (a
/// per-user convenience, like the other panes'). The page makes one, hands it to its PaneDock and to the toggles that
/// bring a hidden pane back; each listener unsubscribes when it goes.
/// </summary>
public sealed class PaneDockState
{
    private readonly IJSRuntime _js;
    private readonly string _key;
    private readonly DockLayout _defaults;

    public PaneDockState(IJSRuntime js, string key, DockLayout defaults)
    {
        _js = js;
        _key = key;
        _defaults = defaults;
        Layout = defaults;
    }

    public event Action? Changed;

    public DockLayout Layout { get; private set; }

    /// <summary>The layout this browser kept for the page (or the defaults).</summary>
    public async Task LoadAsync()
    {
        DockLayout? kept = null;
        try
        {
            var text = await _js.InvokeAsync<string?>("sab.recall", _key);
            kept = string.IsNullOrEmpty(text) ? null : JsonSerializer.Deserialize<DockLayout>(text);
        }
        catch (JsonException)
        {
            // a kept layout from an older page: the defaults
        }
        Layout = DockLayout.Recalled(kept, _defaults);
        Changed?.Invoke();
    }

    public bool IsShown(string id) => Layout.IsShown(id);

    public Task ToggleAsync(string id) => ApplyAsync(Layout.Toggle(id));

    public Task HideAsync(string id) => ApplyAsync(Layout.Hide(id));

    public Task ShowAsync(string id) => ApplyAsync(Layout.Show(id));

    public Task MoveAsync(string id, DockSide side) => ApplyAsync(Layout.MoveTo(id, side));

    public Task WidthAsync(DockSide side, double width) => ApplyAsync(Layout.WithWidth(side, width));

    public Task SplitAsync(DockSide side, int upper, double fraction) => ApplyAsync(Layout.Split(side, upper, fraction));

    /// <summary>A layout put in use (drawn at once) and kept for next time.</summary>
    public async Task ApplyAsync(DockLayout layout)
    {
        Layout = layout;
        Changed?.Invoke();
        await _js.InvokeVoidAsync("sab.remember", _key, JsonSerializer.Serialize(layout));
    }
}
