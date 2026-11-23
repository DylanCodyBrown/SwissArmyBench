namespace SwissArmyBench.Web.Api.Settings;

/// <summary>What joining a team needs first (the Git extension), in words.</summary>
public sealed record TeamNeeds(string Name, string Words, bool Installable = false);
