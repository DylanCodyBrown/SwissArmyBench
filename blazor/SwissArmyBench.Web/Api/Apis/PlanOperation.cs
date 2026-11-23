namespace SwissArmyBench.Web.Api.Apis;

/// <summary>One operation as the method it becomes; readable: it reads as a table.</summary>
public sealed record PlanOperation(string Name, string Method, string Path, bool Readable);
