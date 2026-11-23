using System.Text.Json;

namespace SwissArmyBench.Web.Api.Connections;

/// <summary>A connection kind's Add connection form (GET /connections/types), or a saved connection as its form (GET
/// /connections/{name}): the code, its fields by part, its passwords, its ways to sign in, a vault's secrets; a Python
/// connection's three boxes (Code, Catalog and Read's commands) and the variables they read.</summary>
public sealed record ConnectionForm(
    string Id,
    string Label,
    string Group,
    string Connection,
    string Kind,
    string? Dialect,
    string Variable,
    string Code,
    IReadOnlyList<FormField> Fields,
    IReadOnlyDictionary<string, IReadOnlyList<string>> FieldOrder,
    IReadOnlyList<string> Secrets,
    IReadOnlyList<PackageNeed> Packages,
    IReadOnlyList<LocalNote> Local,
    JsonElement Catalog,
    string Note = "",
    WritesInfo? Writes = null,
    string? Name = null,
    string? Description = null,
    JsonElement? Read = null,
    IReadOnlyList<VariableRead>? Reads = null,
    int? RowLimit = null,
    IReadOnlyDictionary<string, FieldPlace>? FieldPlaces = null,
    IReadOnlyList<string>? Options = null,
    IReadOnlyDictionary<string, IReadOnlyList<string>>? Choices = null,
    IReadOnlyList<SignInWay>? SignIns = null,
    LocalNote? KeyringNote = null,
    string SecretsFrom = "",
    IReadOnlyList<VaultMapping>? VaultMapping = null,
    bool VaultAll = false,
    MissingPackages? Missing = null,
    string? InstallHere = null,
    FormSummary? Summary = null);
