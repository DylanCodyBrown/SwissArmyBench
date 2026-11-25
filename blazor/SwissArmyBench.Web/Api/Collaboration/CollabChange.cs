namespace SwissArmyBench.Web.Api.Collaboration;

/// <summary>The object an activity line is about: its kind and its name (never a value).</summary>
public sealed record CollabChange(string Kind, string Name);
