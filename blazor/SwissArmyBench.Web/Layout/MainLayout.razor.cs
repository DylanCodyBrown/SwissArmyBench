using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Layout;

public partial class MainLayout : IDisposable
{
    private const string Opening = "opening";
    private const string SignedOut = "signed-out";
    private const string Ready = "ready";

    // The brand's red (grid.css --accent): Fluent UI's accent, so its buttons and switches wear the app's colour.
    private const string LightAccent = "#c8102e";
    private const string DarkAccent = "#ff6b73";

    private string _state = Opening;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Inject]
    private ThemeState Theme { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    [Inject]
    private RailState RailState { get; set; } = default!;

    [Inject]
    private ProjectState Project { get; set; } = default!;

    private string AccentColour => Theme.IsDark ? DarkAccent : LightAccent;

    protected override async Task OnInitializedAsync()
    {
        if (!await Js.InvokeAsync<bool>("sab.openSession"))
        {
            _state = SignedOut;
            return;
        }
        Theme.Changed += StateHasChanged;
        await Theme.StartAsync();
        await Live.StartAsync();
        _state = Ready;
        await Task.WhenAll(RailState.StartAsync(), Project.RefreshAsync());
    }

    public void Dispose()
    {
        Theme.Changed -= StateHasChanged;
        GC.SuppressFinalize(this);
    }
}
