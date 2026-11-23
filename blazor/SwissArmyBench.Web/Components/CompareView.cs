namespace SwissArmyBench.Web.Components;

/// <summary>A grid drawn as one side of a compare: the compare's id and the side ("left" or "right").</summary>
public sealed record CompareView(string Id, string Side);
