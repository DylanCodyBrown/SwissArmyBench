using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;

namespace SwissArmyBench.Web.Pages.Catalog;

/// <summary>The tree's keys (the classic dataBrowse.ts): the arrows move through the lines shown, Home and End go
/// to the first and last, Right opens (then goes in), Left closes (then goes up), Enter runs a table's first action
/// or opens a group.</summary>
public partial class CatalogTree
{
    private async Task KeyAsync(KeyboardEventArgs e)
    {
        var shown = Visible();
        if (shown.Count == 0)
        {
            return;
        }
        var at = shown.FindIndex(n => n.Key == Selected);
        var node = at >= 0 ? shown[at] : null;
        switch (e.Key)
        {
            case "ArrowDown":
                await GoAsync(shown[Math.Min(shown.Count - 1, at + 1)]);
                break;
            case "ArrowUp":
                await GoAsync(shown[Math.Max(0, at - 1)]);
                break;
            case "Home":
                await GoAsync(shown[0]);
                break;
            case "End":
                await GoAsync(shown[^1]);
                break;
            case "ArrowRight" when node?.Children is { } kids:
                if (!node.IsOpen(_opened))
                {
                    await ToggleAsync(node, true);
                }
                else if (kids.Count > 0)
                {
                    await GoAsync(kids[0]);
                }
                break;
            case "ArrowLeft" when node is not null:
                if (node.IsOpen(_opened))
                {
                    await ToggleAsync(node, false);
                }
                else if (ParentOf(node) is { } parent)
                {
                    await GoAsync(parent);
                }
                break;
            case "Enter" when node is not null:
                if (node.Kind is "table" or "item" or "column")
                {
                    await RunFirstAsync(node);
                }
                else
                {
                    await ToggleAsync(node);
                }
                break;
            default:
                break;
        }
    }

    private async Task GoAsync(TreeNode node)
    {
        await SelectAsync(node);
        StateHasChanged();
        var key = node.Key.Replace("\\", "\\\\", StringComparison.Ordinal).Replace("\"", "\\\"", StringComparison.Ordinal);
        await Js.InvokeVoidAsync("sab.focus", $".db-tree [data-key=\"{key}\"]");
    }
}
