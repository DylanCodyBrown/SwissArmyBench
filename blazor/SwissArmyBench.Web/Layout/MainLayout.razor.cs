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
    private NavigationManager Navigation { get; set; } = default!;

    [Inject]
    private ThemeState Theme { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    [Inject]
    private RailState RailState { get; set; } = default!;

    [Inject]
    private ProjectState Project { get; set; } = default!;

    [Inject]
    private BetaState Beta { get; set; } = default!;

    [Inject]
    private TourState Tour { get; set; } = default!;

    [Inject]
    private ProjectSetup Setup { get; set; } = default!;

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
        await OpenStartGridAsync();
        await Task.WhenAll(RailState.StartAsync(), Project.RefreshAsync(), Beta.StartAsync(), Tour.StartAsync(), Setup.LoadAsync());
    }

    /// <summary>A classic address's #grid= (a pushed table, the desktop app's file): that grid on the Grids page.</summary>
    private async Task OpenStartGridAsync()
    {
        var grid = await Js.InvokeAsync<string>("sab.takeStartGrid");
        if (!string.IsNullOrEmpty(grid))
        {
            Navigation.NavigateTo($"grids?grid={Uri.EscapeDataString(grid)}", replace: true);
        }
    }

    public void Dispose()
    {
        Theme.Changed -= StateHasChanged;
        GC.SuppressFinalize(this);
    }
}
