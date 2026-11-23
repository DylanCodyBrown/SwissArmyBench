using System.Text.Json;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api.Grids;

namespace SwissArmyBench.Web.Pages.Grids.Steps;

/// <summary>
/// What every step's form shares (the classic stepForms.ts Form: its element and read()): the columns entering the
/// step, the step's parameters to start from (an edited step's, or a tool's preset), and Read, which gives the
/// parameters to save or throws <see cref="StepFormException"/> with what to fix.
/// </summary>
public abstract class StepFormBase : ComponentBase
{
    /// <summary>The columns entering the step (an edited step offers what it sees, not the view's).</summary>
    [Parameter, EditorRequired]
    public IReadOnlyList<GridColumn> Columns { get; set; } = [];

    /// <summary>The step's parameters to start from (an object; empty for a new step with no preset).</summary>
    [Parameter]
    public JsonElement Start { get; set; }

    /// <summary>The server's grid id (the filter's values and the bucket's range are asked of it).</summary>
    [Parameter]
    public string Grid { get; set; } = string.Empty;

    /// <summary>The step being edited (its values are the ones entering it), or null for a new one.</summary>
    [Parameter]
    public int? Index { get; set; }

    public abstract Dictionary<string, object?> Read();

    protected string Text(string name, string fallback = "") =>
        Start.ValueKind == JsonValueKind.Object && Start.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString()! : fallback;

    protected string Raw(string name, string fallback = "") =>
        Start.ValueKind == JsonValueKind.Object && Start.TryGetProperty(name, out var value) && value.ValueKind is not JsonValueKind.Null and not JsonValueKind.Undefined
            ? (value.ValueKind == JsonValueKind.String ? value.GetString()! : value.GetRawText())
            : fallback;

    protected bool Flag(string name) => Start.ValueKind == JsonValueKind.Object && Start.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.True;

    protected IReadOnlyList<string> Names(string name) =>
        Start.ValueKind == JsonValueKind.Object && Start.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.Array
            ? value.EnumerateArray().Where(v => v.ValueKind == JsonValueKind.String).Select(v => v.GetString()!).ToList()
            : [];

    protected IEnumerable<JsonElement> Items(string name) =>
        Start.ValueKind == JsonValueKind.Object && Start.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.Array ? value.EnumerateArray() : [];

    protected string TypeOf(string column) => Columns.FirstOrDefault(c => c.Name == column)?.Type ?? "VARCHAR";

    /// <summary>A number typed in a box, or the reason it is not one.</summary>
    protected static double Number(string typed, string what)
    {
        if (double.TryParse(typed.Trim(), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var number))
        {
            return number;
        }
        throw new StepFormException($"{what}: \"{typed}\" is not a number.");
    }
}
