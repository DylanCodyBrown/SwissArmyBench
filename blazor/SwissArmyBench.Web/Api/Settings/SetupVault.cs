namespace SwissArmyBench.Web.Api.Settings;

/// <summary>A key vault on Set up this computer: its state, words, what it gives, its error, its fix.</summary>
public sealed record SetupVault(
    string Name,
    string State,
    string Words,
    string Error = "",
    string Gives = "",
    SetupFix? Fix = null);
