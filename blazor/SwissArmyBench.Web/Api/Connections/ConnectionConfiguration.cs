namespace SwissArmyBench.Web.Api.Connections;

/// <summary>A connection's configuration as the detail shows it: its settings, sign-in, where each password and variable comes from (never a value).</summary>
public sealed record ConnectionConfiguration(
    IReadOnlyList<NamedValue> Settings,
    IReadOnlyList<PasswordPlace> Passwords,
    string Type = "",
    string Description = "",
    string Kind = "database",
    string Dialect = "",
    string? SignIn = null,
    IReadOnlyList<VariablePlace>? Variables = null,
    IReadOnlyList<VaultEntry>? VaultEntries = null,
    bool VaultAll = false,
    int? RowLimit = null);
