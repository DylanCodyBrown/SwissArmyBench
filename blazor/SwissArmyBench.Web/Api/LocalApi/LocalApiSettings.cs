namespace SwissArmyBench.Web.Api.LocalApi;

/// <summary>API.py's settings in its header: its name, description, target and base path.</summary>
public sealed record LocalApiSettings(string Name, string Description, string Target, string BasePath);
