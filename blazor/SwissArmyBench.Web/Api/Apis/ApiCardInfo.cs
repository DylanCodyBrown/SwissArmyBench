using System.Text.Json;

namespace SwissArmyBench.Web.Api.Apis;

/// <summary>An API's card on the APIs page: its name, title and version, base address, operations and tables, sign-in, calls, where its document came from, a problem, its file.</summary>
public sealed record ApiCardInfo(
    string Name,
    string Title,
    string BaseUrl,
    int Operations,
    string Auth,
    ApiCardSource Source,
    string? Version = null,
    IReadOnlyList<JsonElement>? Tables = null,
    ApiCalls? Calls = null,
    string? Problem = null,
    string? File = null);
