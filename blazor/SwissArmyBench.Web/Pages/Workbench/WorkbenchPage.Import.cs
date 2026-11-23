using SwissArmyBench.Web.Api.Workbench;

namespace SwissArmyBench.Web.Pages.Workbench;

// Import… (the classic workbenchBars.ts and catalogRail.ts's Import from a project…, projectImport.ts): documents
// from another project folder or a loose file into the open project, each copy opened on its page; blades into the
// library, the Blades pane read again.
public partial class WorkbenchPage
{
    private string? _importKind;
    private BladesPane? _bladesPane;

    private async Task ImportedAsync(Imported? done)
    {
        var kind = _importKind;
        _importKind = null;
        if (done is null)
        {
            return;
        }
        if (kind == "blades" && _bladesPane is not null)
        {
            await _bladesPane.LoadAsync();
        }
        foreach (var copy in done.Documents)
        {
            await OpenPathAsync(copy.Full);
        }
        await LoadTreeAsync();
        if (done.Documents.Count > 0)
        {
            await FollowAddressAsync();
        }
    }
}
