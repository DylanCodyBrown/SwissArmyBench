using System.Text.Json;

namespace SwissArmyBench.Web.Api.Apis;

/// <summary>POST /actions/run: the envelope's status, kind, pages and records, or its error.</summary>
public sealed record ActionRun(
    bool Ok,
    int Status,
    string Kind,
    ActionPaging Paging,
    IReadOnlyList<JsonElement>? Records = null,
    ActionError? Error = null);
