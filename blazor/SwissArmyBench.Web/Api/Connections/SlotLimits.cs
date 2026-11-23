namespace SwissArmyBench.Web.Api.Connections;

/// <summary>How many queries run at once on a connection, how many of them the agent's, and how long one waits (seconds).</summary>
public sealed record SlotLimits(int Total, int Agent, int Wait);
