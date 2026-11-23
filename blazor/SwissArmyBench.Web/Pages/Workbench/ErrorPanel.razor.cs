using System.Text.Json;

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

public partial class ErrorPanel
{
    // A call stack this short opens by itself.
    private const int OpenStackFrames = 6;

    // The traceback's end the agent reads (the classic errorText's slice).
    private const int TracebackTail = 3000;

    private ShownMenu? _menu;

    [Inject]
    private AgentInboxClient Inbox { get; set; } = default!;

    [Inject]
    private Dialogs Dialogs { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    /// <summary>The run's error_detail as the server sent it.</summary>
    [Parameter, EditorRequired]
    public JsonElement Detail { get; set; }

    /// <summary>Python's own traceback text, its colours kept.</summary>
    [Parameter]
    public string Traceback { get; set; } = string.Empty;

    /// <summary>The document the error happened in (the agent's title says it).</summary>
    [Parameter]
    public string Document { get; set; } = "the Workbench";

    [Parameter]
    public EventCallback<RunErrorFix> OnFix { get; set; }

    [Parameter]
    public EventCallback<RunErrorFrame> OnGoTo { get; set; }

    [Parameter]
    public EventCallback<string> OnOpenGrid { get; set; }

    private RunError? Error => Detail.ValueKind == JsonValueKind.Object ? Detail.Deserialize<RunError>(ApiClient.Json) : null;

    private RunErrorEntry? Entry => Error?.Chain.LastOrDefault();

    private RunErrorFrame? YourFrame => Entry is { YourFrame: { } at } entry && at < entry.Frames.Count ? entry.Frames[at] : null;

    /// <summary>The frames in order, each run of library or standard library frames as one folded row.</summary>
    public static IReadOnlyList<(bool Library, IReadOnlyList<RunErrorFrame> Frames)> StackRuns(IReadOnlyList<RunErrorFrame> frames) =>
        frames
            .Select((f, i) => (Frame: f, Library: f.Where is "library" or "stdlib", Index: i))
            .Aggregate(new List<(bool Library, List<RunErrorFrame> Frames)>(), (runs, f) =>
            {
                if (f.Library && runs.Count > 0 && runs[^1].Library)
                {
                    runs[^1].Frames.Add(f.Frame);
                }
                else
                {
                    runs.Add((f.Library, [f.Frame]));
                }
                return runs;
            })
            .Select(r => (r.Library, (IReadOnlyList<RunErrorFrame>)r.Frames))
            .ToList();

    private static string LibraryNames(IReadOnlyList<RunErrorFrame> frames) =>
        string.Join(", ", frames.Select(f => (f.Module.Length > 0 ? f.Module : FilePaths.Name(FilePaths.Folder(f.File) ?? "a library")).Split('.')[0]).Distinct());

    private static string FrameLabel(RunErrorFrame f)
    {
        var place = f.Where == "cell" ? $"cell [{f.Cell?.ToString() ?? "?"}]" : FilePaths.Name(f.File ?? string.Empty) is { Length: > 0 } file ? file : f.Module;
        var function = f.Function.Length > 0 && f.Function != "<module>" ? $"{f.Function}(), " : string.Empty;
        return $"{function}{place}, line {f.Line}";
    }

    private static string FixIcon(RunErrorFix fix) => fix.Kind switch
    {
        "install" => "import",
        "define" => "play",
        "cell" or "table" => "plus",
        _ => "edit",
    };

    private Task GoToAsync(RunErrorFrame? frame) => frame is null ? Task.CompletedTask : OnGoTo.InvokeAsync(frame);

    /// <summary>The error as the agent reads it: what, where, the plain words, the values, the code, the traceback's end.</summary>
    private string ErrorText()
    {
        if (Entry is not { } last)
        {
            return OutputReader.Plain(Traceback);
        }
        List<string> lines = [$"{last.Type}{(last.Message.Length > 0 ? $": {last.Message}" : string.Empty)}"];
        lines.AddRange(new[]
        {
            Error?.Where is { Length: > 0 } where ? $"Where: {where}" : null,
            last.Hint.Length > 0 ? $"Python's hint: {last.Hint}" : null,
            last.Explanation.Length > 0 ? $"What it means: {last.Explanation}" : null,
            YourFrame is { Code.Length: > 0 } at ? $"The failing line: {at.Code.Trim()}" : null,
            YourFrame is { Values.Count: > 0 } v ? $"Values at that moment: {string.Join("; ", v.Values.Select(x => $"{x.Expr} = {x.Repr} ({x.Type})"))}" : null,
            YourFrame is { Locals.Count: > 0 } l ? $"{l.Function}()'s variables: {string.Join("; ", l.Locals.Select(x => $"{x.Name} = {x.Repr}"))}" : null,
            last.Fixes.Count > 0 ? $"Fixes the Workbench offered: {string.Join("; ", last.Fixes.Select(f => f.Title.Replace("`", string.Empty)))}" : null,
        }.OfType<string>());
        lines.AddRange(Error!.Chain.Take(Error.Chain.Count - 1).Select(e => $"It followed: {e.Type}: {e.Message}"));
        var plain = OutputReader.Plain(Traceback).Trim();
        if (plain.Length > 0)
        {
            lines.AddRange(["Traceback (its end):", plain[Math.Max(0, plain.Length - TracebackTail)..]]);
        }
        return string.Join('\n', lines);
    }

    private async Task SendAsync(bool withQuestion)
    {
        var title = $"An error in {Document}{(Error?.Where is { Length: > 0 } where ? $" ({where})" : string.Empty)}";
        var note = string.Empty;
        if (withQuestion)
        {
            if (await Dialogs.AskTextAsync("Send to the agent", title, "Your question", string.Empty, "Send") is not { } question)
            {
                return;
            }
            note = question.Trim();
        }
        try
        {
            await Inbox.SendAsync("error", title, ErrorText(), note);
            await Notes.SayAsync("Sent to the agent");
        }
        catch (ApiException error)
        {
            Notes.Error(error);
        }
    }

    private async Task CopyTracebackAsync() => await Js.InvokeVoidAsync("sab.copy", OutputReader.Plain(Traceback));

    private void ShowMenu(MouseEventArgs at) => _menu = new ShownMenu("This error",
    [
        new MenuEntry("Send this error to the agent", "agent", () => SendAsync(false)),
        new MenuEntry("Send it with a question…", "agent", () => SendAsync(true)),
        new MenuEntry("Copy the error", "copy", async () =>
        {
            await Js.InvokeVoidAsync("sab.copy", ErrorText());
            await Notes.SayAsync("Copied");
        }),
    ], at.ClientX, at.ClientY);
}
