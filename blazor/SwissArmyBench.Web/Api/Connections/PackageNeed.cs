namespace SwissArmyBench.Web.Api.Connections;

/// <summary>A Python package a connection's code imports, and whether it is installed here.</summary>
public sealed record PackageNeed(string Module, string Pip, bool Installed);
