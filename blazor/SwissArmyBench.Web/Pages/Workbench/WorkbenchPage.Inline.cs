using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.App;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

// Ghost text in the editors (the classic inlineCompletion.ts): the providers the open project's mode declares (GitHub
// Copilot's, while that extension is on), handed to every editor of the page; the status bar's "Completions: <name> ·
// <word>", a click turning it on or off; read again on inline_completion_changed and project_changed.
public partial class WorkbenchPage
{
    private IReadOnlyList<InlineProvider> _inline = [];
    private InlineStatus? _inlineStatus;

    [Inject]
    private AppClient AppApi { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    private async Task LoadInlineAsync()
    {
        try
        {
            _inline = (await AppApi.ModeAsync()).Mode.InlineCompletion ?? [];
            _inlineStatus = _inline.FirstOrDefault()?.Status is { } route ? await AppApi.InlineStatusAsync(route) : null;
        }
        catch (ApiException)
        {
            (_inline, _inlineStatus) = ([], null); // no ghost text: the editors complete as before
        }
    }

    private async Task ToggleInlineAsync()
    {
        if (_inline.FirstOrDefault()?.Toggle is { } route && _inlineStatus is { } status)
        {
            await GuardAsync(() => AppApi.InlineToggleAsync(route, !status.On));
            await LoadInlineAsync();
        }
    }

    private void OnInlineNotice(Notice notice)
    {
        if (notice.Type is "inline_completion_changed" or "project_changed")
        {
            _ = InvokeAsync(async () =>
            {
                await LoadInlineAsync();
                StateHasChanged();
            });
        }
    }
}
