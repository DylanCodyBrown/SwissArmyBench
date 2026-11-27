using SwissArmyBench.Web.Api.Workbench;

namespace SwissArmyBench.Web.State;

/// <summary>Export outline, the same from every page: ARCHITECTURE.md is the app's own outline of the project, written
/// only when its bytes change; one edited by hand since is kept and said, and replaced only on the user's word
/// (never silently). What to say afterwards comes back with the answer.</summary>
public static class OutlineExport
{
    public static async Task<(ProjectOutline Done, string Words)> RunAsync(ExportsClient exports, Dialogs dialogs)
    {
        var done = await exports.OutlineAsync();
        if (!done.Edited)
        {
            return (done, $"{done.File} {(done.Written ? "written" : "is up to date")}");
        }
        var words = done.Said ?? $"{done.File} was edited by hand: your edit is kept.";
        if (!await dialogs.AskYesNoAsync("Export outline", words, "Replace it", danger: true, no: "Keep mine"))
        {
            return (done, $"{done.File} kept as you edited it");
        }
        done = await exports.OutlineAsync(replace: true);
        return (done, $"{done.File} replaced with the new outline");
    }
}
