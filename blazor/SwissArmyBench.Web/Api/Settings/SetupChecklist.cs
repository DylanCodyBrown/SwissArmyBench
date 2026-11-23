namespace SwissArmyBench.Web.Api.Settings;

/// <summary>GET /library/setup: Set up this computer's checklist: the vaults, the values to type once, the connections, the shared projects.</summary>
public sealed record SetupChecklist(
    string Heading,
    int Count,
    bool Ready,
    string Words,
    IReadOnlyList<SetupVault> Vaults,
    IReadOnlyList<SetupValue> Values,
    IReadOnlyList<SetupConnection> Connections,
    IReadOnlyList<SetupProject> Projects);
