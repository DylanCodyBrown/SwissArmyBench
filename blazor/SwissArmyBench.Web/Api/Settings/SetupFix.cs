namespace SwissArmyBench.Web.Api.Settings;

/// <summary>How a checklist item is fixed: a value typed (a password, a local value, a keyring one), its words.</summary>
public sealed record SetupFix(
    string Kind,
    string Label,
    string? How = null,
    string? Name = null,
    string? Connection = null);
