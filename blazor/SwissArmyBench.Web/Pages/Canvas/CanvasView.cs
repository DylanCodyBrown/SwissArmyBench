using SwissArmyBench.Web.Api.Canvas;

namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>
/// What one Canvas window shows (the classic canvasPage.ts's module state): the canvas as the server last answered,
/// the page in front, the selection, the layout (Desktop or Phone), its preview width and the zoom. Its helpers read
/// the model; every change is the server's command (CanvasPage sends it).
/// </summary>
public sealed class CanvasView
{
    public const string Desktop = "desktop";
    public const string Phone = "phone";

    // The widths a layout can be previewed at (the built page fits any of them).
    public const double DesktopLowest = 768;
    public const double DesktopWidest = 1920;
    public const double PhoneLowest = 320;
    public const double PhoneWidest = 767;

    private const double DesktopDesign = 1200;
    private const double PhoneDesign = 390;
    private const double LeastZoom = 0.25;
    private const double MostZoom = 4;

    public CanvasState? State { get; set; }

    public string Page { get; set; } = string.Empty;

    public List<string> Selected { get; set; } = [];

    public string Layout { get; set; } = Desktop;

    public double Zoom { get; private set; } = 1;

    public Dictionary<string, double> PreviewWidth { get; } = new() { [Desktop] = DesktopDesign, [Phone] = PhoneDesign };

    public bool Editable => State is { ReadOnly: null, Broken: null };

    /// <summary>The layout's design width: every place is in its pixels.</summary>
    public double PageWidth => State?.Design.GetValueOrDefault(Layout) is { } width and > 0 ? width : Layout == Phone ? PhoneDesign : DesktopDesign;

    /// <summary>How wide the page is shown over its design width: x and w are drawn times this.</summary>
    public double Stretch => PreviewWidth[Layout] / PageWidth;

    public (double Low, double High) Range => Layout == Phone ? (PhoneLowest, PhoneWidest) : (DesktopLowest, DesktopWidest);

    /// <summary>The page in front's items as the layout in front has them.</summary>
    public IReadOnlyList<CanvasNode> Children =>
        State?.Views.GetValueOrDefault(Page)?.GetValueOrDefault(Layout) ?? [];

    public IReadOnlyDictionary<string, string> PageNames =>
        (State?.Model.Pages ?? []).ToDictionary(p => p.Id, p => p.Name);

    public void SetZoom(double next) => Zoom = Math.Max(LeastZoom, Math.Min(MostZoom, Math.Round(next * 100) / 100));

    public double X(double v) => v * Stretch;

    /// <summary>A node anywhere on the canvas (every page, this layout), and its container.</summary>
    public NodePlace? Find(string id) =>
        (State?.Model.Pages ?? [])
            .Select(p => Look(State!.Views.GetValueOrDefault(p.Id)?.GetValueOrDefault(Layout) ?? [], null, id))
            .FirstOrDefault(found => found is not null);

    /// <summary>An item's top-left corner in the page's pixels.</summary>
    public (double X, double Y) Absolute(string id)
    {
        double x = 0;
        double y = 0;
        var at = Find(id);
        while (at is not null)
        {
            x += at.Node.X;
            y += at.Node.Y;
            at = at.Parent is { } parent ? Find(parent.Id) : null;
        }
        return (x, y);
    }

    /// <summary>The deepest container under a point of the page (not <paramref name="skip"/> nor inside it).</summary>
    public CanvasNode? ContainerAt(double px, double py, string? skip)
    {
        CanvasNode? best = null;
        void Walk(IEnumerable<CanvasNode> children, double ox, double oy)
        {
            foreach (var c in children.Where(c => c.Kind == "container" && c.Id != skip))
            {
                var (x, y) = (ox + c.X, oy + c.Y);
                if (px >= x && px <= x + c.W && py >= y && py <= y + c.H)
                {
                    best = c;
                    Walk(c.Children ?? [], x, y);
                }
            }
        }
        Walk(Children, 0, 0);
        return best;
    }

    /// <summary>Where a double-click or Insert puts a widget: the selected container, or the selected widget's.</summary>
    public string? SelectedContainer()
    {
        var at = Selected.Count > 0 ? Find(Selected[0]) : null;
        return at is null ? null : at.Node.Kind == "container" ? at.Node.Id : at.Parent?.Id;
    }

    /// <summary>The grid a node snaps to: its container's columns and width, else the page's.</summary>
    public GridSpec GridFor(CanvasNode? parent)
    {
        var sizing = State!.Model.Sizing;
        return new GridSpec(parent?.Props?.Columns ?? sizing.Columns, sizing.RowHeight, sizing.Gap, parent?.W ?? PageWidth);
    }

    private static NodePlace? Look(IEnumerable<CanvasNode> children, CanvasNode? parent, string id)
    {
        foreach (var child in children)
        {
            if (child.Id == id)
            {
                return new NodePlace(child, parent);
            }
            if (child.Children is { } inner && Look(inner, child, id) is { } found)
            {
                return found;
            }
        }
        return null;
    }
}
