namespace SwissArmyBench.Web.Api.Connections;

/// <summary>What a feature needs that the app's Python lacks, in the one shape the missing-package prompt reads.</summary>
public sealed record MissingPackages(string Feature, IReadOnlyList<string> Packages, string Python, string Command);
