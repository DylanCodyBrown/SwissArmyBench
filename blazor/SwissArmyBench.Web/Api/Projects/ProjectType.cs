using System.Text.Json;

namespace SwissArmyBench.Web.Api.Projects;

/// <summary>A project type, explained for beginners (New project's choice).</summary>
public sealed record ProjectType(
    string Type,
    string Name,
    string Title,
    string ForWhom,
    string Explain,
    string Example,
    string Deliverable,
    JsonElement Make);
