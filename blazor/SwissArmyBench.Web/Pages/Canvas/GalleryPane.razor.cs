using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;

using SwissArmyBench.Web.Api.Widgets;

namespace SwissArmyBench.Web.Pages.Canvas;

public partial class GalleryPane
{
    // The large preview shows after resting this long on a card, this wide, to the card's left.
    private const int HoverMs = 400;
    private const double BigWidth = 496;
    private const double BigGap = 12;
    private const double Edge = 8;

    private string _query = string.Empty;
    private string? _focused;
    private WidgetEntry? _big;
    private (double X, double Y) _bigAt;
    private CancellationTokenSource? _hover;

    [Parameter, EditorRequired]
    public IReadOnlyList<WidgetEntry> Widgets { get; set; } = [];

    [Parameter]
    public bool Editable { get; set; }

    /// <summary>Insert a widget into the selected container (the page knows which).</summary>
    [Parameter]
    public EventCallback<string> OnInsert { get; set; }

    /// <summary>A card is being dragged (its name) or let go (null): the board takes the drop.</summary>
    [Parameter]
    public EventCallback<string?> OnDragging { get; set; }

    [Parameter]
    public EventCallback<string?> OnOpenWidgets { get; set; }

    /// <summary>The card that has the focus: the page's Insert key puts it in.</summary>
    public string? Focused => _focused;

    private IEnumerable<IGrouping<string, WidgetEntry>> Shown => WidgetHeadings
        .Ordered(Widgets.Where(w => WidgetHeadings.Matches(w, _query)))
        .GroupBy(WidgetHeadings.Of);

    private string BigPlace => FormattableString.Invariant($"left: {Math.Max(Edge, _bigAt.X - BigWidth - BigGap)}px; top: max({Edge}px, min({_bigAt.Y}px, calc(100vh - 420px)));");

    private Task OpenWidgetsAsync() => OnOpenWidgets.InvokeAsync(null);

    private async Task DragStartAsync(WidgetEntry widget)
    {
        HidePreview();
        await OnDragging.InvokeAsync(widget.Name);
    }

    private async Task InsertAsync(WidgetEntry widget)
    {
        if (Editable)
        {
            await OnInsert.InvokeAsync(widget.Name);
        }
    }

    private async Task KeyAsync(KeyboardEventArgs e, WidgetEntry widget)
    {
        if (e.Key is "Insert" or "Enter")
        {
            await InsertAsync(widget);
        }
    }

    private async Task HoverAsync(WidgetEntry widget, MouseEventArgs e)
    {
        HidePreview();
        var wait = new CancellationTokenSource();
        _hover = wait;
        try
        {
            await Task.Delay(HoverMs, wait.Token);
        }
        catch (TaskCanceledException)
        {
            return;
        }
        // The card's left edge: the pointer's place less how far in it is (the card is the pane's width).
        _bigAt = (e.ClientX - e.OffsetX, e.ClientY - e.OffsetY);
        _big = widget;
        StateHasChanged();
    }

    private void HidePreview()
    {
        _hover?.Cancel();
        _hover?.Dispose();
        _hover = null;
        _big = null;
    }

    public void Dispose() => HidePreview();
}
