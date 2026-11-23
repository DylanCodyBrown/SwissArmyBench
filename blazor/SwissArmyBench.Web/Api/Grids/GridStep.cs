using System.Text.Json;

namespace SwissArmyBench.Web.Api.Grids;

/// <summary>One step of a grid (filter, sort, columns, rename, group_by...), in plain words too.</summary>
public sealed record GridStep(string Kind, JsonElement Params, string? Id = null, bool Enabled = true, string Description = "");
