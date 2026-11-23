namespace SwissArmyBench.Web.Api.Connections;

/// <summary>Where one of a connection's passwords comes from (never its value).</summary>
public sealed record PasswordPlace(string Name, string From, string? Vault = null, string? Secret = null);
