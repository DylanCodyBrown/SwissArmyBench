namespace SwissArmyBench.Web.Api.Connections;

/// <summary>POST /connections/source: the code with a password pointed at a variable, and the secret's name now.</summary>
public sealed record PointedAnswer(string Code, string Secret);
