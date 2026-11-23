namespace SwissArmyBench.Web.Api.LocalApi;

/// <summary>The local sandbox API running: its port, address, since when.</summary>
public sealed record LocalApiRunning(int Port, string Url, string Since);
