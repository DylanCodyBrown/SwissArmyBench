using System.Text.Json;

namespace SwissArmyBench.Web.Pages.Grids;

/// <summary>A step's editor asked for: its kind, the parameters it starts from (an edited step's or a tool's
/// preset), and the step's place when one is edited.</summary>
public sealed record StepRequest(string Kind, JsonElement Start, int? Index);
