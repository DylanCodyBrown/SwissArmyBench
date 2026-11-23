namespace SwissArmyBench.Web.Api.Connections;

/// <summary>A connection's slots now: what runs and waits (the agent's share too), its limits, in words ("Running 3 of 8 · 1 waiting").</summary>
public sealed record SlotStatus(
    string Connection,
    int Running,
    int Waiting,
    int AgentRunning,
    int AgentWaiting,
    SlotLimits Limits,
    string Words,
    string FullWords);
