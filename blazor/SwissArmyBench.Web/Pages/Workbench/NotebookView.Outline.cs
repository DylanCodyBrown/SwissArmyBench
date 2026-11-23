using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Workbench;

namespace SwissArmyBench.Web.Pages.Workbench;

// The notebook's Outline beside its cells (Notebook mode's panel): read from the server's run order as the cells
// change, a line's click going to its cell.
public partial class NotebookView
{
    private NotebookFlow? _flow;

    /// <summary>The Outline shows beside the cells.</summary>
    public bool OutlineShown { get; private set; }

    public async Task ToggleOutlineAsync()
    {
        OutlineShown = !OutlineShown;
        if (OutlineShown)
        {
            await ReadFlowAsync();
        }
    }

    private async Task ReadFlowAsync()
    {
        if (!OutlineShown)
        {
            return;
        }
        try
        {
            _flow = await Workbench.FlowAsync(_kept.Cells.Where(c => !c.IsAppCell).Select(c => c.ToSaved()).ToList());
        }
        catch (ApiException)
        {
            _flow = new NotebookFlow([], []); // said as no headings: the Outline is read again on the next change
        }
    }

    private Task GoToNumberAsync(int number)
    {
        if (_kept.Cells.FirstOrDefault(c => c.Number == number) is { } cell)
        {
            (_selected, _focusNext) = (cell, cell);
        }
        return Task.CompletedTask;
    }

    private Task GoToTablesAsync()
    {
        if (_kept.Cells.FirstOrDefault(c => c.IsAppCell) is { } first)
        {
            _selected = first;
        }
        return Task.CompletedTask;
    }
}
