using System.Text.Json;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Analyze;

// What the Analyze page shows, for the agent's app_screen (State/ScreenState): the analysis in its form, the table
// and the columns picked for each slot, what is still missing, and the board's cards by title and kind. Names only:
// no option's value, no card's body.
public partial class AnalyzePage
{
    private AnalyzeForm? _form;

    [Inject]
    private ScreenState Screen { get; set; } = default!;

    protected override void OnAfterRender(bool firstRender)
    {
        if (firstRender)
        {
            Screen.Show(this, ScreenPart);
        }
        Screen.Touch();
    }

    private static List<string> Picked(JsonElement columns, string slot) =>
        columns.ValueKind == JsonValueKind.Object && columns.TryGetProperty(slot, out var picked)
            ? picked.ValueKind switch
            {
                JsonValueKind.String => [picked.GetString() ?? string.Empty],
                JsonValueKind.Array => picked.EnumerateArray().Where(c => c.ValueKind == JsonValueKind.String).Select(c => c.GetString() ?? string.Empty).ToList(),
                _ => [],
            }
            : [];

    private Dictionary<string, object?> ScreenPart() => new()
    {
        ["analyze"] = new Dictionary<string, object?>
        {
            ["analysis"] = _analysis,
            ["table"] = _analysis is null ? null : _form?.Plan?.Dataset,
            ["form"] = _analysis is null
                ? null
                : _form?.Plan?.Slots.Select(slot => new Dictionary<string, object?> { ["slot"] = slot.Label, ["columns"] = Picked(_form.Plan.Columns, slot.Key) }).ToList(),
            ["missing"] = _analysis is null ? null : _form?.Plan?.Missing,
            ["cards"] = _cards.Select(card => new Dictionary<string, object?> { ["title"] = card.Title, ["kind"] = card.Kind }).ToList(),
        },
    };
}
