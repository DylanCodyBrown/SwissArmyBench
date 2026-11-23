using System.Text.Json;

namespace SwissArmyBench.Web.Api.LocalApi;

/// <summary>POST /local-api/call: an endpoint's answer: its status, time, rows, body, a refusal's words and its line.</summary>
public sealed record LocalApiAnswer(
    int Status,
    double Ms,
    JsonElement Body,
    long? Rows = null,
    string? Error = null,
    int? Line = null,
    string? Where = null);
