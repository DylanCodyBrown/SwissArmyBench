namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>POST /scripts/definition's answer: where the name at the cursor is defined.</summary>
public sealed record IdeDefinitions(IReadOnlyList<IdePlace> Definitions);
