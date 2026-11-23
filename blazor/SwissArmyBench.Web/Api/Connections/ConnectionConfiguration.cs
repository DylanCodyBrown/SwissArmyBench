namespace SwissArmyBench.Web.Api.Connections;

/// <summary>A connection's configuration as the detail shows it: its settings and where its passwords come from.</summary>
public sealed record ConnectionConfiguration(IReadOnlyList<NamedValue> Settings, IReadOnlyList<PasswordPlace> Passwords, string Type = "", string Description = "");
