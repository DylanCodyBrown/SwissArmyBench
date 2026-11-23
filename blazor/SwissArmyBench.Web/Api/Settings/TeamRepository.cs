namespace SwissArmyBench.Web.Api.Settings;

/// <summary>A GitHub repository the user can join: its name, private or not, when last pushed.</summary>
public sealed record TeamRepository(string Repository, bool Private = false, string Pushed = "");
