using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Canvas;

// What the Canvas shows, for the agent's app_screen (State/ScreenState): the canvas, the page and layout in front,
// what is selected (each item's id, kind, widget and a container's title), the zoom, Play and full screen. Names
// only: no property's value.
public partial class CanvasPage
{
    private const int Percent = 100;

    [Inject]
    private ScreenState Screen { get; set; } = default!;

    protected override void OnAfterRender(bool firstRender)
    {
        if (firstRender)
        {
            Screen.Show(this, ScreenPart);
        }
        Screen.Touch();
    }

    private Dictionary<string, object?> ScreenPart() => new()
    {
        ["canvas"] = _view.State is { } state
            ? new Dictionary<string, object?>
            {
                ["path"] = state.Path,
                ["page"] = _view.PageNames.GetValueOrDefault(_view.Page, _view.Page),
                ["pages"] = state.Model.Pages.Select(p => p.Name).ToList(),
                ["layout"] = _view.Layout,
                ["selection"] = _view.Selected
                    .Select(id => _view.Find(id)?.Node)
                    .OfType<SwissArmyBench.Web.Api.Canvas.CanvasNode>()
                    .Select(node => new Dictionary<string, object?> { ["id"] = node.Id, ["kind"] = node.Kind, ["widget"] = node.Widget, ["title"] = node.Props?.Title })
                    .ToList(),
                ["items"] = _view.Children.Count,
                ["zoom"] = (int)Math.Round(_view.Zoom * Percent),
                ["playing"] = _playUrl is not null,
                ["full_screen"] = _full,
            }
            : null,
    };
}
