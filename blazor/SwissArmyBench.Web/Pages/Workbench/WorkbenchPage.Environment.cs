using Microsoft.JSInterop;

namespace SwissArmyBench.Web.Pages.Workbench;

// The Environment as the page's right-hand pane (the classic environmentPage.ts environmentPane, beside the code as
// RStudio's): closed until the status bar's Environment opens it, remembered per page; its Hide closes it again.
public partial class WorkbenchPage
{
    private bool _showEnvironment;

    private async Task RecallEnvironmentAsync() =>
        _showEnvironment = await Js.InvokeAsync<string?>("sab.recall", $"{Page}.environment") == "1";

    private async Task ToggleEnvironmentAsync()
    {
        _showEnvironment = !_showEnvironment;
        await Js.InvokeVoidAsync("sab.remember", $"{Page}.environment", _showEnvironment ? "1" : "0");
    }
}
