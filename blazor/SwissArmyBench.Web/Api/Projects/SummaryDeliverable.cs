namespace SwissArmyBench.Web.Api.Projects;

/// <summary>The project type's deliverable (its contract.json's), on Home's summary: its words and its files.</summary>
public sealed record SummaryDeliverable(string Type, string Deliverable, IReadOnlyList<DeliverableFile> Files);
