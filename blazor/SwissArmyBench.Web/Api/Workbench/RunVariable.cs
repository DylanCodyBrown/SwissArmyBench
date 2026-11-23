namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>One of a script's variables: why it is needed ("line 23", a connection, "added"), whether it reads like a
/// password (no plain value offered), and where it comes from (env, value, vault).</summary>
public sealed record RunVariable(
    string Name,
    string Why,
    bool LooksSecret,
    string From,
    string? Value = null,
    string? Vault = null,
    string? Secret = null);
