using SwissArmyBench.Web.Api.Workbench;

namespace SwissArmyBench.Web.Pages.Workbench;

/// <summary>A heading of the Blades pane (Your blades, a starter family) and its blades; open when it is yours.</summary>
public sealed record BladeGroup(string Name, IReadOnlyList<BladeSummary> Blades, bool Open);
