using System.Text.Json;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Workbench;

namespace SwissArmyBench.Web.Pages.Workbench;

public partial class BladesPane
{
    private IReadOnlyList<BladeSummary> _mine = [];
    private IReadOnlyList<StarterFamily> _starters = [];
    private string _search = string.Empty;
    private Exception? _error;

    [Inject]
    private WorkbenchClient Workbench { get; set; } = default!;

    /// <summary>A blade's line to put into the code.</summary>
    [Parameter]
    public EventCallback<string> OnInsert { get; set; }

    /// <summary>Your blades first, then each starter family; only the ones whose name or words hold the search.</summary>
    private IEnumerable<BladeGroup> Groups =>
        new[] { new BladeGroup("Your blades", Matching(_mine), true) }
            .Concat(_starters.Select(f => new BladeGroup(f.Family, Matching(f.Blades), _search.Length > 0)))
            .Where(g => g.Blades.Count > 0);

    protected override Task OnInitializedAsync() => LoadAsync();

    private async Task LoadAsync()
    {
        try
        {
            _mine = (await Workbench.BladesAsync()).Blades;
            _starters = (await Workbench.StartersAsync()).Families;
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private List<BladeSummary> Matching(IEnumerable<BladeSummary> blades) =>
        blades
            .Where(b => _search.Length == 0
                || b.Name.Contains(_search, StringComparison.OrdinalIgnoreCase)
                || (b.Description ?? string.Empty).Contains(_search, StringComparison.OrdinalIgnoreCase))
            .OrderBy(b => b.Name, StringComparer.OrdinalIgnoreCase)
            .ToList();

    /// <summary>A blade as one line of code (the classic bladeEditor.ts bladeLine): a connection by sab.connection, any
    /// other by sab.blade, assigned to its variable when it makes one.</summary>
    private static string LineOf(BladeSummary blade)
    {
        var call = $"sab.{(blade.Connection is null ? "blade" : "connection")}({JsonSerializer.Serialize(blade.Name)})";
        return blade.Kind is "vault" or "secret" || string.IsNullOrEmpty(blade.Variable) ? call : $"{blade.Variable} = {call}";
    }
}
