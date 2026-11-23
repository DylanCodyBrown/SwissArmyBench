namespace SwissArmyBench.Web.Api.App;

/// <summary>A provider's status for the status bar: its name, on or off, ready, and its word.</summary>
public sealed record InlineStatus(string Name, bool On, bool Ready, string Words);
