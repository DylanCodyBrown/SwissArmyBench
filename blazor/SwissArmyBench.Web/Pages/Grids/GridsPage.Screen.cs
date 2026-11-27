using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Grids;

// What the Tables page shows, for the agent's app_screen (State/ScreenState): the table in front, the tabs, a split.
public partial class GridsPage
{
    [Inject]
    private ScreenState Screen { get; set; } = default!;

    private Dictionary<string, object?> ScreenPart() => new()
    {
        ["table"] = _info is { } info
            ? TableScreen.Of(info, _selection, _total, _onScreen)
                .Append(new("tabs", _tabs.Select(t => t.Dataset).ToList()))
                .Append(new("split", _split?.Where(_infos.ContainsKey).Select(id => _infos[id].Dataset).ToList()))
                .ToDictionary(part => part.Key, part => part.Value)
            : null,
        ["tabs"] = _info is null ? _tabs.Select(t => new Dictionary<string, object?> { ["title"] = t.Dataset, ["kind"] = "table" }).ToList() : null,
    };
}
