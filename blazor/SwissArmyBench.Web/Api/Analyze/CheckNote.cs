namespace SwissArmyBench.Web.Api.Analyze;

/// <summary>One of Check this table's notes on the table (its level: info or warn).</summary>
public sealed record CheckNote(string Level, string Text);
