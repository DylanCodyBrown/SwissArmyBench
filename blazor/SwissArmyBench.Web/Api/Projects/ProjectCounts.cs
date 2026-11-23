namespace SwissArmyBench.Web.Api.Projects;

/// <summary>How many documents and tables a project holds (a card's line).</summary>
public sealed record ProjectCounts(int Notebooks = 0, int Scripts = 0, int Apps = 0, int Tables = 0);
