using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Settings;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Components;

// The editor's own right-click menu (the classic lazy/codeEditor.ts): Send to the agent and Send to the agent with a
// question… (the selection, or the cursor's line, with where it is from), the page's own lines for this editor, Insert
// variable… in SQL (codeEditor.js), and Leave a note… while beta mode is on.
public partial class CodeEditor
{
    // Beta mode is asked once a page: the editors made after share the answer.
    private static Task<bool>? _betaAsked;

    [Inject]
    private AgentInboxClient Inbox { get; set; } = default!;

    [Inject]
    private SettingsClient SettingsApi { get; set; } = default!;

    [Inject]
    private Dialogs Dialogs { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    /// <summary>Where the code is from ("cell 2 of sums.ipynb", "rates.py"): set, the menu offers Send to the agent.</summary>
    [Parameter]
    public string? AgentWhere { get; set; }

    [Parameter]
    public IReadOnlyList<EditorMenuAction> MenuActions { get; set; } = [];

    [Parameter]
    public EventCallback<EditorMenuPick> OnMenuAction { get; set; }

    private async Task<object> MenuOptionsAsync() => new
    {
        agent = AgentWhere is not null,
        beta = await BetaOnAsync(),
        actions = MenuActions.Select(a => new { id = a.Id, label = a.Label }).ToList(),
    };

    private async Task<bool> BetaOnAsync()
    {
        _betaAsked ??= AskBetaAsync();
        return await _betaAsked;
    }

    private async Task<bool> AskBetaAsync()
    {
        try
        {
            return (await SettingsApi.BetaAsync()).On;
        }
        catch (ApiException)
        {
            return false;
        }
    }

    [JSInvokable]
    public Task Menu(string id, int line, int end, string text) => InvokeAsync(() => id switch
    {
        "sendToAgent" => SendAsync(line, end, text, false),
        "sendToAgentAsk" => SendAsync(line, end, text, true),
        "leaveNote" => LeaveNoteAsync(),
        _ => OnMenuAction.InvokeAsync(new EditorMenuPick(id, line)),
    });

    private async Task SendAsync(int line, int end, string text, bool withQuestion)
    {
        if (text.Trim().Length == 0)
        {
            return; // a blank line, nothing selected: nothing to send
        }
        var title = $"{AgentWhere}, {(line == end ? $"line {line}" : $"lines {line} to {end}")}";
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
            await Inbox.SendAsync("code", title, text, note);
            await Notes.SayAsync("Sent to the agent");
        }
        catch (ApiException error)
        {
            Notes.Error(error);
        }
    }

    private async Task LeaveNoteAsync()
    {
        var text = await Dialogs.AskTextAsync("Leave a note", "What happened, in your own words: it goes in the beta log.", "Note", string.Empty, "Leave the note");
        if (!string.IsNullOrWhiteSpace(text))
        {
            await SettingsApi.BetaNoteAsync(text);
            await Notes.SayAsync("Noted.");
        }
    }
}
