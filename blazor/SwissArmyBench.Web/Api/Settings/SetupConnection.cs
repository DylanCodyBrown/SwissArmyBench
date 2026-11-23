namespace SwissArmyBench.Web.Api.Settings;

/// <summary>A connection on Set up this computer: its state, words and the passwords that could move to a vault.</summary>
public sealed record SetupConnection(string Name, string State, string Words, IReadOnlyList<MoveToVault> MoveToVault);
