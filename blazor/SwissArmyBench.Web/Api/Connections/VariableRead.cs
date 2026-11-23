namespace SwissArmyBench.Web.Api.Connections;

/// <summary>An environment variable a Python connection's code reads (POST /connections/variables): whether the code
/// needs it (no default of its own), whether it is a secret, and whether it is set on this computer.</summary>
public sealed record VariableRead(string Name, bool Required, bool Secret, bool Set);
