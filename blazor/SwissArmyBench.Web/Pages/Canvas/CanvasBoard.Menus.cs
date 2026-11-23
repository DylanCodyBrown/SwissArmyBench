using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api.Canvas;

namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>The board's right-click menus (the classic canvasMenus.ts): empty grid's Insert container and Insert widget
/// ▸; a container's Insert widget ▸, Insert container, Scrollable, Resizable by viewers, Delete; a widget's Edit
/// widget, Replace widget ▸, Delete; each ending with the run group. A read-only canvas: the run group alone.</summary>
public partial class CanvasBoard
{
    // A container inserted into another is at most this big.
    private const double InsertedWidth = 200;
    private const double InsertedHeight = 120;

    private async Task BoardMenuAsync(MouseEventArgs e)
    {
        var module = await ModuleAsync();
        _box = await module.InvokeAsync<BoardBox>("rect", _board);
        var (x, y) = PagePoint(e.ClientX, e.ClientY);
        var own = View.Editable
            ? new List<CanvasMenuItem>
            {
                new("Insert container", () => OnSend("add_container", new() { ["page"] = View.Page, ["x"] = CanvasGrid.Round(x), ["y"] = CanvasGrid.Round(y) })),
                new("Insert widget", Pick: widget => OnInsert.InvokeAsync(new InsertRequest(widget, null, CanvasGrid.Round(x), CanvasGrid.Round(y)))),
            }
            : [];
        await OnMenu.InvokeAsync(new OpenMenu(e.ClientX, e.ClientY, [.. own, .. RunGroup(own.Count > 0)]));
    }

    private async Task NodeMenuAsync(NodeMenuAt at)
    {
        if (!View.Selected.Contains(at.Node.Id))
        {
            await OnSelect.InvokeAsync([at.Node.Id]);
        }
        var items = !View.Editable ? [.. RunGroup(false)] : at.Node.Kind == "container" ? ContainerItems(at.Node) : WidgetItems(at.Node);
        await OnMenu.InvokeAsync(new OpenMenu(at.ClientX, at.ClientY, items));
    }

    private List<CanvasMenuItem> ContainerItems(CanvasNode node)
    {
        var p = node.Props ?? new ContainerProps();
        return
        [
            new("Insert widget", Pick: widget => OnInsert.InvokeAsync(new InsertRequest(widget, node.Id, null, null))),
            new("Insert container", () => OnSend("add_container", new()
            {
                ["page"] = View.Page,
                ["parent"] = node.Id,
                ["w"] = Math.Min(InsertedWidth, node.W),
                ["h"] = Math.Min(InsertedHeight, node.H),
            })),
            new("Scrollable", () => SetContainerAsync(node, "scrollable", !p.Scrollable), Checked: p.Scrollable),
            new("Resizable by viewers", () => SetContainerAsync(node, "resizable", !p.Resizable), Checked: p.Resizable),
            new("Delete", () => RemoveAsync(node.Id)),
            .. RunGroup(true),
        ];
    }

    private List<CanvasMenuItem> WidgetItems(CanvasNode node) =>
    [
        new("Edit widget", () => OnEditWidget.InvokeAsync(node.Widget)),
        new("Replace widget", Pick: widget => OnSend("replace_widget", new() { ["id"] = node.Id, ["widget"] = widget })),
        new("Delete", () => RemoveAsync(node.Id)),
        .. RunGroup(true),
    ];

    private Task SetContainerAsync(CanvasNode node, string property, bool on) =>
        OnSend("set_container", new() { ["id"] = node.Id, ["props"] = new Dictionary<string, object?> { [property] = on } });
}
