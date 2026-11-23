namespace SwissArmyBench.Web.Api.Connections;

/// <summary>A saved connection's summary: which of its passwords are saved (never a value).</summary>
public sealed record FormSummary(IReadOnlyDictionary<string, bool>? Secrets = null);
