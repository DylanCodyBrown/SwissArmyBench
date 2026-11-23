using Microsoft.JSInterop;

namespace SwissArmyBench.Web.Pages.Grids.Open;

/// <summary>What shell.js's fileDrop calls when a file is dropped on the page, or a table pasted: the Grids page opens it.</summary>
public sealed class DropTarget
{
    private readonly GridsPage _page;

    public DropTarget(GridsPage page)
    {
        _page = page;
    }

    [JSInvokable]
    public Task Dropped(int id, string file) => _page.DroppedAsync(id, file);

    [JSInvokable]
    public Task PastedTable(string text) => _page.PastedTableAsync(text);
}
