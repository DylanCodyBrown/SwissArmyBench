namespace SwissArmyBench.Web.Api.App;

/// <summary>An area's footer mark ("↑3 to push", "↓2 behind", "Conflicts: 2"): its words, its state, its project.</summary>
public sealed record AreaMark(string Words, string State, string? Title = null, string? Name = null);
