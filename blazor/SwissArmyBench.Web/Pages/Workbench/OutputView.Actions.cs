using System.Text.Json;
using System.Text.RegularExpressions;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

// An output's actions (the classic workbenchOutputs.ts): a picture or a figure's Send to Analyze (a card of its own,
// the note's Show going to it), a table result's Open as grid (the kernel still holds it as Out[n]), and a long
// traceback's first and last frames with the middle behind Show N more frames.
public partial class OutputView
{
    // A traceback longer than this shows its first and last frames.
    private const int FoldFrames = 24;

    private bool _allFrames;

    [Inject]
    private WorkbenchClient Workbench { get; set; } = default!;

    [Inject]
    private PythonSession Session { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    [GeneratedRegex(@"<table[\s>]", RegexOptions.IgnoreCase)]
    private static partial Regex TableTag();

    private IReadOnlyList<string> Frames =>
        Output.TryGetProperty("traceback", out var lines) && lines.ValueKind == JsonValueKind.Array
            ? lines.EnumerateArray().Select(l => l.GetString() ?? string.Empty).ToList()
            : [];

    /// <summary>A result's number (Out[n]): a table result opens as a grid by it.</summary>
    private int? ResultCount =>
        OutputReader.Type(Output) == "execute_result" && Output.TryGetProperty("execution_count", out var count) && count.ValueKind == JsonValueKind.Number
            ? count.GetInt32()
            : null;

    private static bool IsTable(string html) => TableTag().IsMatch(html);

    private async Task SendAsync(string kind, string body)
    {
        try
        {
            var sent = await Workbench.SendCardAsync(kind, body, $"From {Document}");
            await Notes.SayAsync("Sent to Analyze", "Show", () =>
            {
                Nav.NavigateTo(sent.Card is { } card ? $"analyze?card={Uri.EscapeDataString(card)}" : "analyze");
                return Task.CompletedTask;
            });
        }
        catch (ApiException error)
        {
            Notes.Error(error);
        }
    }

    private async Task OpenResultAsync(int count)
    {
        if (Session.Kernel is not { } kernel)
        {
            return;
        }
        try
        {
            var opened = await Workbench.OpenGridAsync(kernel, count, null);
            await Notes.SayAsync($"{opened.Dataset} is open as a grid.");
        }
        catch (ApiException error)
        {
            Notes.Error(error);
        }
    }
}
