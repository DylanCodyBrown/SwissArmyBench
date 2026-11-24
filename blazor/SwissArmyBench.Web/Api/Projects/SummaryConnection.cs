namespace SwissArmyBench.Web.Api.Projects;

/// <summary>A connection the project uses, on Home's summary: its type, its card's status word and its colour.</summary>
public sealed record SummaryConnection(string Name, string Type = "", string Status = "", string Colour = "");
