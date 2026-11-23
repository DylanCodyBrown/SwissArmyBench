namespace SwissArmyBench.Web.Api.Relationships;

/// <summary>GET /relationships/scope?scope=project: whether a project is open, the tables it uses, and in words what
/// the project scope leaves out.</summary>
public sealed record RelationshipScope(bool Project, IReadOnlyList<string> Tables, string Words = "");
