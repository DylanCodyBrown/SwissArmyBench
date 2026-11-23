using SwissArmyBench.Web.Api.Grids;

namespace SwissArmyBench.Web.Pages.Grids.Tabs;

/// <summary>The tabs of one connection's tables (or one kind: Files, Pasted, Queries...), under its head. Key is
/// "c:&lt;connection&gt;" or "k:&lt;kind&gt;"; Name null means the row has no groups (no connection's table is
/// open), so no head is drawn.</summary>
public sealed record TabGroup(string Key, string? Name, string? Connection, IReadOnlyList<GridListItem> Tabs);
