namespace SwissArmyBench.Web.Api.Settings;

/// <summary>GET /beta: beta mode, what decided it, and what the log holds.</summary>
public sealed record BetaStatus(bool On, string SetBy, int Files, long Bytes, int Pictures);
