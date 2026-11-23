namespace SwissArmyBench.Web.Api.Analyze;

/// <summary>One analysis as Check this table ranks it: its status (now, fixes, no), why, and its button's verb.</summary>
public sealed record RankedAnalysis(
    string Analysis,
    string Label,
    string Name,
    string Get,
    string Status,
    string Reason,
    string Button);
