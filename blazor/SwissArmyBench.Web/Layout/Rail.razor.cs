using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Routing;

using SwissArmyBench.Web.Navigation;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Layout;

public partial class Rail : IDisposable
{
    private const int MostShown = 99;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    [Inject]
    private RailState RailState { get; set; } = default!;

    private string ToggleWords => RailState.Names ? "Icons only" : "Show names";

    /// <summary>The area the address names (a page off the rail marks the area it belongs to).</summary>
    private string? Current => Areas.AreaOfPath(Nav.ToBaseRelativePath(Nav.Uri));

    /// <summary>The base's areas, Canvas and Widgets only while a mode offers them, an extension's areas before
    /// Session (each drawn as a page of its own from its data).</summary>
    private IEnumerable<RailArea> Shown
    {
        get
        {
            var extensions = RailState.ExtensionAreas
                .Select(extra => new RailArea(extra.Area, extra.Name, extra.Icon, $"x-{extra.Area}", $"/workspace?open={extra.Area}"));
            var shown = Areas.All
                .Where(area => RailState.CanvasOn || area.Area is not (Areas.Canvas or Areas.Widgets))
                .Where(area => RailState.CodeAppOn || area.Area != Areas.CodeApp)
                .ToList();
            var session = shown.FindIndex(area => area.Area == Areas.Session);
            return shown
                .Take(session)
                .Concat(extensions)
                .Concat(shown.Skip(session));
        }
    }

    protected override void OnInitialized()
    {
        Nav.LocationChanged += OnLocationChanged;
        RailState.Changed += OnRailChanged;
    }

    private string LabelOf(RailArea area) =>
        area.Area == Areas.Session && RailState.Unseen > 0 ? $"Session, {RailState.Unseen} new" : area.Name;

    private Task ToggleNamesAsync() => RailState.SetNamesAsync(!RailState.Names);

    private void OnLocationChanged(object? sender, LocationChangedEventArgs e) => StateHasChanged();

    private void OnRailChanged() => InvokeAsync(StateHasChanged);

    public void Dispose()
    {
        Nav.LocationChanged -= OnLocationChanged;
        RailState.Changed -= OnRailChanged;
        GC.SuppressFinalize(this);
    }
}
