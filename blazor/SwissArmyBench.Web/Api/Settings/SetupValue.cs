namespace SwissArmyBench.Web.Api.Settings;

/// <summary>A value this computer needs: its words, its kind, and the fix (a box).</summary>
public sealed record SetupValue(string Name, string Kind, string Words, SetupFix Fix, string? Connection = null);
