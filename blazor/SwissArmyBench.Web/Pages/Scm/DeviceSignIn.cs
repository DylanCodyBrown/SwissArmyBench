using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Git;

namespace SwissArmyBench.Web.Pages.Scm;

/// <summary>GitHub's device flow as both sign-ins use it (the classic scmPage.ts githubSignIn and teamSignIn): the
/// code shown, GitHub's page opened, asked again at GitHub's interval until it is typed; the user's own (the agent
/// never signs in).</summary>
public sealed class DeviceSignIn
{
    private const int DefaultInterval = 5;

    private readonly GitClient _git;

    public DeviceSignIn(GitClient git)
    {
        _git = git;
    }

    /// <summary>The flow started: its code and address (shown at once), then asked until it ends; the words when it
    /// ends otherwise than signed in.</summary>
    public async Task<string?> RunAsync(Func<DeviceFlow, Task> started, Func<bool> stillWanted, CancellationToken cancel)
    {
        var flow = await _git.StartDeviceFlowAsync();
        await started(flow);
        var interval = flow.Interval;
        while (stillWanted())
        {
            await Task.Delay(TimeSpan.FromSeconds(Math.Max(1, interval)), cancel);
            DevicePoll said;
            try
            {
                said = await _git.PollDeviceFlowAsync();
            }
            catch (ApiException error)
            {
                return error.Refusal.Error;
            }
            if (said.State == "signed_in")
            {
                return null;
            }
            if (said.State != "pending")
            {
                return said.Words ?? said.State;
            }
            interval = said.Interval ?? DefaultInterval;
        }
        return null;
    }
}
