namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>An instance's In or Event wired: its source, or its actions; null takes the wire away.</summary>
public sealed record WireChange(string Id, string Port, object? Wire);
