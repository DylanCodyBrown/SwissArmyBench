namespace SwissArmyBench.Web.Api.Settings;

/// <summary>A connection's password that could come from a vault instead: the secret and the vaults offered.</summary>
public sealed record MoveToVault(string Secret, IReadOnlyList<string> Vaults);
