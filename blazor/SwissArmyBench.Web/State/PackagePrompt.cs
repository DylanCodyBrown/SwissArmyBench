using SwissArmyBench.Web.Api;

namespace SwissArmyBench.Web.State;

/// <summary>One missing-package prompt on screen: what is missing, how it is installed and what runs after.</summary>
/// <param name="Missing">The packages and the feature that needs them.</param>
/// <param name="Install">Where they go: the app's own Python unless the place passed its own installer.</param>
/// <param name="Then">What the user was doing, run again once they are installed.</param>
public sealed record PackagePrompt(MissingPackages Missing, Func<MissingPackages, Task> Install, Func<Task>? Then)
{
    /// <summary>"Install a and b?" (the owner's words: "&lt;feature&gt; will not work without &lt;package&gt; Install now?").</summary>
    public string Title => $"Install {Missing.Listed}?";

    public string Sentence => $"{Missing.Feature} will not work without {Missing.Listed}.";
}
