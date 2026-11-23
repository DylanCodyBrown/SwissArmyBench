using Microsoft.AspNetCore.Components;

namespace SwissArmyBench.Web.Pages.Workbench;

// A blade opens as a tab of the Scripts page (the classic bladeDoc, the blade IDE's seam): ?blade=<name>, the Blades
// pane's click, New blade, a copy or a rename following its tab.
public partial class WorkbenchPage
{
    [Parameter]
    public string? Blade { get; set; }

    /// <summary>A blade's tab: brought to the front when open, else opened after the one in front.</summary>
    private async Task OpenBladeAsync(string name, bool fresh = false)
    {
        if (_documents.FirstOrDefault(d => d.Blade == name) is { } open)
        {
            _layout.Show(open.Key);
        }
        else
        {
            AddDocument(new OpenDocument(++_nextKey, false) { Blade = name, Fresh = fresh });
        }
        await FollowAddressAsync();
    }

    /// <summary>Saved under a new name, or copied as the user's own: the tab shows that blade now.</summary>
    private async Task BladeRenamedAsync(OpenDocument doc, string name)
    {
        if (doc.Blade == name)
        {
            return;
        }
        doc.Dirty = false;
        if (_documents.Any(d => d != doc && d.Blade == name))
        {
            await OpenBladeAsync(name);
            return;
        }
        doc.Blade = name;
        await FollowAddressAsync();
    }

    private string? BladeAddress => Front?.Blade is { } blade ? $"{Page}?blade={Uri.EscapeDataString(blade)}" : null;
}
