namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>POST /scripts/references's answer: every use across the project.</summary>
public sealed record IdeReferences(IReadOnlyList<IdePlace> References);
