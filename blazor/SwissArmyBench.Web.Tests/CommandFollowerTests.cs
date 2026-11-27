using System.Text.Json;

using Bunit;

using Microsoft.Extensions.DependencyInjection;

using SwissArmyBench.Web.Layout;
using SwissArmyBench.Web.State;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>The agent's workbench_window followed: a command of the page's palette runs as the user's own, the page's
/// own answers come first, and the window answers the server with the result or the reason.</summary>
public sealed class CommandFollowerTests : AppTestContext
{
    private readonly CannedServer _server = new CannedServer().Answer("POST /workbench/window/r1", """{"received": true}""");
    private int _ran;

    public CommandFollowerTests()
    {
        Services.AddScoped(_ => new HttpClient(_server) { BaseAddress = new Uri("http://127.0.0.1:9/") });
    }

    private IReadOnlyList<PaletteCommand> PageCommands() =>
    [
        new("view.files", "View", "Show or hide Files", () => { _ran++; return Task.CompletedTask; }, "Ctrl+B"),
        new("run.cell", "Run", "Run the cell", () => Task.CompletedTask, WhyNot: "Select a cell first"),
    ];

    private static Task<CommandAnswer?> PageAnswers(string command, JsonElement args) =>
        Task.FromResult(command == "documents" ? new CommandAnswer(new { documents = new[] { "load.py" } }, "/made-up/load.py", "load.py") : null);

    private string Answered(IRenderedComponent<CommandFollower> follower)
    {
        follower.WaitForAssertion(() => Assert.Contains(_server.Asked, a => a.Route == "POST /workbench/window/r1"));
        return _server.Asked.Last(a => a.Route == "POST /workbench/window/r1").Body;
    }

    private IRenderedComponent<CommandFollower> Follower()
    {
        var commands = Get<Commands>();
        commands.SetPageCommands(PageCommands);
        commands.SetPageAnswers(PageAnswers);
        return Render<CommandFollower>();
    }

    [Fact]
    public void APaletteCommandRunsAndTheWindowAnswers()
    {
        var follower = Follower();

        Get<LiveUpdates>().Notice("""{"type": "workbench_command", "id": "r1", "command": "view.files", "args": {}}""");

        Assert.Contains("\"ran\":\"view.files\"", Answered(follower), StringComparison.Ordinal);
        Assert.Equal(1, _ran);
    }

    [Fact]
    public void ThePagesOwnAnswerComesFirstWithWhereItHappened()
    {
        var follower = Follower();

        Get<LiveUpdates>().Notice("""{"type": "workbench_command", "id": "r1", "command": "documents"}""");

        var said = Answered(follower);
        Assert.Contains("\"documents\":[\"load.py\"]", said, StringComparison.Ordinal);
        Assert.Contains("\"path\":\"/made-up/load.py\"", said, StringComparison.Ordinal);
    }

    [Fact]
    public void CommandsListsThePalette()
    {
        var follower = Follower();

        Get<LiveUpdates>().Notice("""{"type": "workbench_command", "id": "r1", "command": "commands"}""");

        var said = Answered(follower);
        Assert.Contains("\"id\":\"view.files\"", said, StringComparison.Ordinal);
        Assert.Contains("\"why_not\":\"Select a cell first\"", said, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("run.cell", "Select a cell first")]
    [InlineData("kitchen.sink", "This page has no command")]
    public void ACommandThatCannotRunSaysWhy(string command, string words)
    {
        var follower = Follower();

        Get<LiveUpdates>().Notice($$"""{"type": "workbench_command", "id": "r1", "command": "{{command}}"}""");

        var said = Answered(follower);
        Assert.Contains("\"error\":", said, StringComparison.Ordinal);
        Assert.Contains(words, said, StringComparison.Ordinal);
    }

    [Fact]
    public async Task TheFollowerLetsGoOfTheLiveNoticesAsync()
    {
        var live = Get<LiveUpdates>();
        var before = Subscribers(live, nameof(LiveUpdates.NoticeArrived));
        var follower = Follower();

        Assert.NotNull(follower);
        await DisposeComponentsAsync();
        Assert.Equal(before, Subscribers(live, nameof(LiveUpdates.NoticeArrived)));
    }
}
