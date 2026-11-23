namespace SwissArmyBench.Web.Api.Settings;

/// <summary>The Joined row's word: what needs doing (Pull, changes to push, conflicts, an error); none means up to date.</summary>
public sealed record TeamSync(string State, string Words);
