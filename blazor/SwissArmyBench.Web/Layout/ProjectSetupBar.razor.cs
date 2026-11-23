using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Projects;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Layout;

public partial class ProjectSetupBar : IDisposable
{
    // Done says itself this long, then goes (its fade is the stylesheet's, in its last second).
    private static readonly TimeSpan _fadeAfter = TimeSpan.FromSeconds(6);

    private bool _details;
    private ProjectInstalls? _fading;

    [Inject]
    private ProjectSetup Setup { get; set; } = default!;

    [Inject]
    private WorkbenchClient Workbench { get; set; } = default!;

    [Inject]
    private Dialogs Dialogs { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    /// <summary>How long done stays on screen (a test's shorter).</summary>
    [Parameter]
    public TimeSpan? Fade { get; set; }

    protected override void OnInitialized() => Setup.Changed += Redraw;

    private void Redraw()
    {
        if (Setup.Now is { State: ProjectSetup.Done, Restart: false } now && Setup.Shown && !ReferenceEquals(now, _fading))
        {
            _fading = now;
            _ = FadeAsync(now);
        }
        InvokeAsync(StateHasChanged);
    }

    private async Task FadeAsync(ProjectInstalls done)
    {
        await Task.Delay(Fade ?? _fadeAfter);
        if (ReferenceEquals(Setup.Now, done))
        {
            Setup.Close();
        }
    }

    private void ToggleDetails() => _details = !_details;

    private async Task RetryAsync()
    {
        try
        {
            await Setup.RunAsync();
        }
        catch (ApiException error)
        {
            Notes.Error(error);
        }
    }

    /// <summary>The project's one Python session restarted onto the new libraries: asked first (every variable goes).</summary>
    private async Task RestartAsync(string kernel)
    {
        const string Words = "Restart the project's Python session to use the new libraries? Every variable is cleared, for every notebook and script of the project.";
        if (!await Dialogs.AskYesNoAsync("Restart", Words, "Restart"))
        {
            return;
        }
        try
        {
            await Workbench.RestartAsync(kernel);
            Setup.Close();
        }
        catch (ApiException error)
        {
            Notes.Error(error);
        }
    }

    private static string StatusIcon(string status) => status switch
    {
        "installed" => "check",
        "installing" => "import",
        "failed" => "problem",
        _ => "clock",
    };

    private static string StatusWords(string status) => status switch
    {
        "installed" => "Installed",
        "installing" => "Installing…",
        "failed" => "Failed",
        _ => "Waiting",
    };

    public void Dispose()
    {
        Setup.Changed -= Redraw;
        GC.SuppressFinalize(this);
    }
}
