namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>One kind of a file type that has several (a diagram's: flowchart, class, sequence...): its id and words.</summary>
public sealed record NewFileVariant(string Id, string Label);
