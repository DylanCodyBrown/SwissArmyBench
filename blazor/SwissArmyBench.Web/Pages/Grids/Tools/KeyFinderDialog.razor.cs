using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Grids;
using SwissArmyBench.Web.Api.Relationships;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Grids.Tools;

public partial class KeyFinderDialog
{
    private IReadOnlyList<KeyFinderTarget> _targets = [];
    private string _target = string.Empty;
    private KeyFinderResult? _result;
    private bool _running;
    private Exception? _error;

    [Inject]
    private GridsClient Grids { get; set; } = default!;

    [Inject]
    private RelationshipsClient Relationships { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Parameter, EditorRequired]
    public string Grid { get; set; } = string.Empty;

    [Parameter, EditorRequired]
    public string Dataset { get; set; } = string.Empty;

    [Parameter]
    public EventCallback OnClose { get; set; }

    protected override async Task OnInitializedAsync()
    {
        try
        {
            _targets = (await Grids.KeyFinderTargetsAsync(Grid)).Grids;
            _target = _targets.FirstOrDefault(t => !t.Self)?.Grid ?? string.Empty;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task FindAsync()
    {
        _running = true;
        try
        {
            _result = await Grids.KeyFinderAsync(Grid, _target);
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
        _running = false;
    }

    private async Task AddAsync(KeyPair pair)
    {
        try
        {
            // A join goes from its many side to its one side: "one to many" means this column is the key.
            var join = pair.Relationship.StartsWith("one to many", StringComparison.Ordinal)
                ? new Join(pair.TargetDataset, [pair.TargetColumn], Dataset, [pair.SourceColumn])
                : new Join(Dataset, [pair.SourceColumn], pair.TargetDataset, [pair.TargetColumn]);
            await Relationships.AddAsync([join]);
            _ = Notes.SayAsync($"Added {Dataset}.{pair.SourceColumn} → {pair.TargetDataset}.{pair.TargetColumn} to the relationships.");
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }
}
