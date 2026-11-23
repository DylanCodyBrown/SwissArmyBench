using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.App;
using SwissArmyBench.Web.Api.SessionLog;
using SwissArmyBench.Web.Api.Settings;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Settings;

public partial class SettingsPage
{
    /// <summary>What an agent needs to connect (the classic MCP_PROMPT, word for word).</summary>
    private const string McpPrompt =
        "Connect the Swiss Army Bench MCP server so you can work on my local data:\n"
        + "1. Run: claude mcp add --scope user swissarmybench -- swissarmybench-mcp\n"
        + "   (another agent: add an MCP server over stdio whose command is swissarmybench-mcp)\n"
        + "2. Reconnect your MCP servers (/mcp in Claude Code).\n"
        + "3. Call its guide tool first; it explains the app and its tools.";

    private Exception? _error;
    private GatesAnswer? _gates;
    private bool _follow = true;

    [Inject]
    private ThemeState Theme { get; set; } = default!;

    [Inject]
    private AppClient App { get; set; } = default!;

    [Inject]
    private SettingsClient Settings { get; set; } = default!;

    [Inject]
    private SessionLogClient SessionLog { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    protected override async Task OnInitializedAsync()
    {
        await Js.InvokeVoidAsync("sab.setTitle", "Settings");
        await RunAsync(async () => _gates = await App.GatesAsync());
        await RunAsync(async () => _follow = (await SessionLog.ListingAsync("agent", changesOnly: true)).Follow);
    }

    private void Failed(Exception error)
    {
        _error = error;
        StateHasChanged();
    }

    private Task EveryFeatureAsync(ChangeEventArgs e) => RunAsync(async () =>
    {
        await Settings.SetEveryFeatureAsync(e.Value is true);
        _gates = await App.GatesAsync();
    });

    private Task FollowAsync(ChangeEventArgs e) => RunAsync(async () => _follow = (await SessionLog.SetFollowAsync(e.Value is true)).Follow);

    private async Task CopyPromptAsync()
    {
        if (await Js.InvokeAsync<bool>("sab.copy", McpPrompt))
        {
            await Notes.SayAsync("Copied.");
        }
        else
        {
            _error = new ApiException(0, new Refusal("The browser blocked the clipboard."), string.Empty);
        }
    }

    private async Task RunAsync(Func<Task> work)
    {
        try
        {
            await work();
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }
}
