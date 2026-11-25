using SwissArmyBench.Web.Api.Collaboration;
using SwissArmyBench.Web.Api.Grids;

namespace SwissArmyBench.Web.Pages.Grids;

/// <summary>The table in front as the objects a note can name (State/PageObjects): the table and its columns.</summary>
public static class TableObjects
{
    public static IReadOnlyList<CollabReference> Of(GridInfo? info) => info is null
        ? []
        : [
            new("table", info.Dataset, string.Empty, info.Dataset),
            .. info.Columns.Select(c => new CollabReference("column", info.Dataset, c.Name, $"{info.Dataset}.{c.Name}")),
        ];
}
