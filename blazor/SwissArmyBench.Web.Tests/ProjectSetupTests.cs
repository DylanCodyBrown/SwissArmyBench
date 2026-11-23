using Bunit;

using Microsoft.Extensions.DependencyInjection;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Projects;
using SwissArmyBench.Web.Layout;
using SwissArmyBench.Web.State;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>The setup bar (Layout/ProjectSetupBar) over the ProjectSetup state service: each state of the
/// project_installs notice as the bar draws it. Made-up project and libraries.</summary>
public sealed class ProjectSetupTests : AppTestContext
{
    private static readonly InstallPackage[] _packages =
    [
        new("pandas_made_up", "data.ipynb and scripts/load.py", "installed"),
        new("tabulate_made_up", "requirements.txt", "installing"),
        new("rich_made_up", "connection Sales (SQL Server)", "waiting"),
    ];

    private static ProjectInstalls Installing() => new(
        ProjectSetup.Installing,
        "Sales Recon",
        Total: 3,
        Done: 1,
        Current: "tabulate_made_up",
        Share: 0.5,
        Packages: _packages,
        Words: "Setting up Sales Recon: installing 2 of 3 · tabulate_made_up");

    public ProjectSetupTests()
    {
        Services.AddScoped<Api.Workbench.WorkbenchClient>();
    }

    [Fact]
    public void WhileInstallingTheBarSaysHowFarWithTheCountAndTheDetailsUnfold()
    {
        var bar = Render<ProjectSetupBar>();
        Assert.Empty(bar.FindAll(".setup-bar"));

        Get<ProjectSetup>().Take(Installing());

        bar.WaitForAssertion(() => Assert.Contains("installing 2 of 3 · tabulate_made_up", bar.Find(".setup-bar-words").TextContent));
        Assert.Equal(50, Get<ProjectSetup>().Percent);
        Assert.Empty(bar.FindAll(".setup-bar-list"));
        bar.Find(".setup-bar-details").Click();
        var rows = bar.FindAll(".setup-bar-package");
        Assert.Equal(3, rows.Count);
        Assert.Contains("data.ipynb and scripts/load.py", rows[0].TextContent);
        Assert.Contains("Installed", rows[0].TextContent);
        Assert.Contains("Installing…", rows[1].TextContent);
        Assert.Contains("Waiting", rows[2].TextContent);
    }

    [Fact]
    public void LookingHasNoCountYetAndHideKeepsAMarkInTheStatusBar()
    {
        var bar = Render<ProjectSetupBar>();
        var status = Render<StatusBar>();
        var setup = Get<ProjectSetup>();
        setup.Take(new ProjectInstalls(ProjectSetup.Checking, "Sales Recon", Words: "Setting up Sales Recon: looking for what it needs…"));
        bar.WaitForAssertion(() => Assert.Single(bar.FindAll(".setup-bar.checking")));
        Assert.Null(setup.Percent);

        setup.Take(Installing());
        bar.Find("button[title^='It keeps going']").Click();

        bar.WaitForAssertion(() => Assert.Empty(bar.FindAll(".setup-bar")));
        status.WaitForAssertion(() => Assert.Contains("Setting up · 1 of 3", status.Find(".status-setup").TextContent));
        status.Find(".status-setup").Click();
        bar.WaitForAssertion(() => Assert.Single(bar.FindAll(".setup-bar")));
    }

    [Fact]
    public void DoneSaysWhatWasInstalledAndGoesByItself()
    {
        var bar = Render<ProjectSetupBar>(p => p.Add(b => b.Fade, TimeSpan.FromMilliseconds(50)));
        var setup = Get<ProjectSetup>();
        setup.Take(Installing());
        var done = Installing() with
        {
            State = ProjectSetup.Done,
            Done = 3,
            Share = 1,
            Words = "Installed 3 libraries · added to requirements.txt",
            Packages = [.. _packages.Select(p => p with { Status = "installed" })],
        };

        setup.Take(done);

        bar.WaitForAssertion(() => Assert.Equal("Installed 3 libraries · added to requirements.txt", bar.Find(".setup-bar-words").TextContent));
        Assert.Equal(100, setup.Percent);
        bar.WaitForAssertion(() => Assert.Empty(bar.FindAll(".setup-bar")), TimeSpan.FromSeconds(5));
        Assert.False(setup.Shown);
    }

    [Fact]
    public void AFailureIsTheOneErrorNoteWithTryAgainAndItsDetails()
    {
        var bar = Render<ProjectSetupBar>();
        var problem = new Refusal(
            "These could not be installed: broken_made_up.",
            Fixes: [new Fix("Try again", "try_again")],
            Details: "error: No solution found: broken_made_up was not found in the package registry");
        Get<ProjectSetup>().Take(Installing() with
        {
            State = ProjectSetup.Failed,
            Problem = problem,
            Words = "1 library could not be installed (broken_made_up); 2 libraries installed",
        });

        bar.WaitForAssertion(() => Assert.Contains("These could not be installed: broken_made_up.", bar.Find(".error-note").TextContent));
        Assert.Contains(bar.FindAll(".error-note button"), b => b.TextContent == "Try again");
        Assert.Contains("No solution found", bar.Find(".error-note-details pre").TextContent);
        Assert.Empty(bar.FindAll("fluent-progress"));
    }

    [Fact]
    public void TheMissingPackagePromptKeepsQuietForWhatThePassIsInstalling()
    {
        var setup = Get<ProjectSetup>();
        setup.Take(Installing());
        var covered = new MissingPackages("Tables", ["Tabulate-Made-Up"], "/made/up/.venv/bin/python", "uv pip install tabulate_made_up");
        var other = covered with { Packages = ["openpyxl"] };

        Assert.True(setup.Covers(covered));
        Assert.False(setup.Covers(other));
        Assert.True(Get<PackagePrompts>().PromptAsync(covered).IsCompletedSuccessfully);
        Assert.Null(Get<PackagePrompts>().Open);
        setup.Take(Installing() with { State = ProjectSetup.Failed, Packages = [.. _packages.Select(p => p with { Status = "failed" })] });
        Assert.False(setup.Covers(covered));
    }

    [Fact]
    public async Task TheBarAndTheStateServiceLetGoWhenTheyCloseAsync()
    {
        var setup = Get<ProjectSetup>();
        var live = Get<LiveUpdates>();
        Render<ProjectSetupBar>();
        Assert.Equal(1, Subscribers(setup, nameof(ProjectSetup.Changed)));

        await DisposeComponentsAsync();
        Assert.Equal(0, Subscribers(setup, nameof(ProjectSetup.Changed)));
        var before = Subscribers(live, nameof(LiveUpdates.NoticeArrived));
        setup.Dispose();
        Assert.Equal(before - 1, Subscribers(live, nameof(LiveUpdates.NoticeArrived)));
    }

    [Fact]
    public void ALibrarysNameIsComparedAsPipComparesIt()
    {
        Assert.Equal("scikit-learn", ProjectSetup.Key("Scikit_Learn"));
        Assert.Equal("psycopg", ProjectSetup.Key("psycopg[binary]>=3"));
    }
}
