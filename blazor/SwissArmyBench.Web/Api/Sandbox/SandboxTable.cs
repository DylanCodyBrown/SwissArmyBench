using System.Text.Json;

namespace SwissArmyBench.Web.Api.Sandbox;

/// <summary>One table of the project's sandbox: its rows and columns, where it came from, the client it is mocked as, its changes.</summary>
public sealed record SandboxTable(
    string Name,
    long Rows,
    IReadOnlyList<SandboxColumn> Columns,
    string SourceWords,
    SandboxMock Client,
    string Sql,
    SandboxChanges Changes,
    string Title,
    string OriginWords = "",
    string? AddedAt = null,
    string? ChangedAt = null,
    bool Mockable = false,
    bool Mocked = false,
    bool Open = false,
    JsonElement? Variant = null);
