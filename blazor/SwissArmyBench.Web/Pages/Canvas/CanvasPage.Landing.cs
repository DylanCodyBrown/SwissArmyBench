using Microsoft.AspNetCore.Components;

namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>What a card of the landing page asks of the canvas it opens (CanvasCard's Play and Export): the address's
/// <c>?do=play</c> or <c>?do=export</c> runs the page's own Play or Export once the canvas is open, and leaves the
/// address (a reload or Back never plays or exports again).</summary>
public partial class CanvasPage
{
    public const string DoPlay = "play";
    public const string DoExport = "export";

    [SupplyParameterFromQuery(Name = "do")]
    public string? Do { get; set; }

    private async Task DoAskedAsync()
    {
        if (Do is not { } asked || Path is null)
        {
            return;
        }
        Nav.NavigateTo($"canvas?path={Uri.EscapeDataString(Path)}", replace: true);
        if (_view.State is null)
        {
            return; // it did not open: its error is on the page
        }
        await (asked switch
        {
            DoPlay => PlayAsync(),
            DoExport => ExportAsync(),
            _ => Task.CompletedTask,
        });
    }
}
