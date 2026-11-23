using System.Text.Json;

namespace SwissArmyBench.Web.Api.Grids;

/// <summary>One column of the table's profile.</summary>
public sealed record TableProfileColumn(
    string Column,
    string Type,
    long Blanks,
    double BlankPercent,
    long Distinct,
    JsonElement Min = default,
    JsonElement Max = default);
