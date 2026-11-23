using System.Globalization;
using System.Text.Json;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Grids;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Grids;

public partial class ColumnCard
{
    private const int MostShown = 8;

    /// <summary>The filter step's conditions this card offers (domain/steps.py FILTER_OPS, in its words).</summary>
    private static readonly (string Op, string Words)[] _conditions =
    [
        ("eq", "equals"),
        ("ne", "does not equal"),
        ("contains", "contains"),
        ("starts_with", "starts with"),
        ("gt", "is greater than"),
        ("lt", "is less than"),
        ("blank", "is blank"),
        ("not_blank", "is not blank"),
    ];

    private static readonly HashSet<string> _noValue = ["blank", "not_blank"];

    private ColumnProfile? _profile;
    private Exception? _error;
    private string _op = "eq";
    private string _value = string.Empty;

    [Inject]
    private GridsClient Grids { get; set; } = default!;

    [Inject]
    private Dialogs Dialogs { get; set; } = default!;

    [Parameter, EditorRequired]
    public string Grid { get; set; } = string.Empty;

    [Parameter, EditorRequired]
    public string Column { get; set; } = string.Empty;

    [Parameter]
    public string Type { get; set; } = string.Empty;

    /// <summary>Every column of the view, in order (Remove keeps the others).</summary>
    [Parameter]
    public IReadOnlyList<string> AllColumns { get; set; } = [];

    /// <summary>A step to add: its kind and its params.</summary>
    [Parameter]
    public EventCallback<(string Kind, object Params)> OnStep { get; set; }

    [Parameter]
    public EventCallback OnClose { get; set; }

    protected override async Task OnParametersSetAsync()
    {
        _profile = null;
        try
        {
            _profile = await Grids.ProfileAsync(Grid, Column);
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private static string Text(JsonElement value) => value.ValueKind switch
    {
        JsonValueKind.String => value.GetString() ?? string.Empty,
        JsonValueKind.Null or JsonValueKind.Undefined => "(blank)",
        _ => value.GetRawText(),
    };

    private Task StepAsync(string kind, object parameters) => OnStep.InvokeAsync((kind, parameters));

    /// <summary>Keep rows where the column meets the condition: a number column's value sent as a number.</summary>
    private Task KeepAsync()
    {
        if (_noValue.Contains(_op))
        {
            return StepAsync("filter", new { column = Column, op = _op });
        }
        object value = double.TryParse(_value, NumberStyles.Float, CultureInfo.InvariantCulture, out var number) && IsNumeric ? number : _value;
        return StepAsync("filter", new { column = Column, op = _op, value });
    }

    private bool IsNumeric => _profile?.Family == "number";

    private async Task RenameAsync()
    {
        var name = await Dialogs.AskTextAsync($"Rename {Column}", "Its new name, as a step (the table itself is not changed).", "Name", Column, "Rename");
        if (!string.IsNullOrWhiteSpace(name) && name != Column)
        {
            await StepAsync("rename", new { mapping = new Dictionary<string, string> { [Column] = name.Trim() } });
        }
    }

    /// <summary>Remove the column: a columns step that keeps every other one, in their order.</summary>
    private Task RemoveAsync() => StepAsync("columns", new { keep = AllColumns.Where(c => c != Column).ToArray() });
}
