using System.Text.Json;

using Bunit;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Layout;
using SwissArmyBench.Web.Navigation;
using SwissArmyBench.Web.State;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>The agent's app_navigate followed by the main window: the "navigate" notice's place as this app's address.</summary>
public sealed class NavigateFollowerTests : AppTestContext
{
    private static Notice NoticeOf(string json)
    {
        using var parsed = JsonDocument.Parse(json);
        return new Notice(parsed.RootElement.GetProperty("type").GetString() ?? string.Empty, parsed.RootElement.Clone());
    }

    [Theory]
    [InlineData("""{"type":"navigate","window":"home","to":"home"}""", "")]
    [InlineData("""{"type":"navigate","window":"home","to":"projects"}""", "?view=projects")]
    [InlineData("""{"type":"navigate","window":"home","to":"analyze"}""", "analyze")]
    [InlineData("""{"type":"navigate","window":"home","to":"data"}""", "catalog")]
    [InlineData("""{"type":"navigate","window":"home","to":"tables"}""", "tables")]
    [InlineData("""{"type":"navigate","window":"home","to":"notebooks"}""", "notebooks")]
    [InlineData("""{"type":"navigate","window":"home","to":"structures"}""", "structures")]
    [InlineData("""{"type":"navigate","window":"home","to":"grid","grid":"g 7"}""", "tables?grid=g%207")]
    [InlineData("""{"type":"navigate","window":"home","to":"connection","name":"Finance Captive"}""", "connections?name=Finance%20Captive")]
    [InlineData("""{"type":"navigate","window":"home","to":"add_connection"}""", "connections?add=1")]
    [InlineData("""{"type":"navigate","window":"home","to":"add_api"}""", "apis?add=1")]
    [InlineData("""{"type":"navigate","window":"home","to":"new_sql"}""", "scripts?new=sql")]
    public void APlaceIsThisAppsAddress(string notice, string address)
    {
        Assert.Equal(address, AgentPlace.AddressOf(NoticeOf(notice)));
    }

    [Fact]
    public void APlaceWithNoPageAndAnotherWindowsNoticeGoNowhere()
    {
        Assert.Null(AgentPlace.AddressOf(NoticeOf("""{"type":"navigate","window":"home","to":"kitchen"}""")));
        Assert.Null(AgentPlace.AddressOf(NoticeOf("""{"type":"navigate","window":"home","to":"grid"}""")));
        Assert.False(AgentPlace.IsForMainWindow(NoticeOf("""{"type":"navigate","window":"workbench","to":"home"}""")));
        Assert.False(AgentPlace.IsForMainWindow(NoticeOf("""{"type":"rail_changed","to":"home"}""")));
    }

    [Fact]
    public void TheMainWindowGoesWhereTheNoticeSays()
    {
        JSInterop.Setup<string?>("sab.windowName").SetResult(WhatsNewState.MainWindow);
        var nav = Get<NavigationManager>();
        var follower = Render<NavigateFollower>();

        Get<LiveUpdates>().Notice("""{"type":"navigate","window":"home","to":"analyze","by":"agent"}""");

        follower.WaitForAssertion(() => Assert.EndsWith("/analyze", nav.Uri, StringComparison.Ordinal));
    }

    [Fact]
    public void TheNotebooksOrScriptsPageTheServerToldFollowsEvenPoppedOut()
    {
        JSInterop.Setup<string?>("sab.windowName").SetResult("sab-scripts");
        var nav = Get<NavigationManager>();
        var follower = Render<NavigateFollower>();

        Get<LiveUpdates>().Notice("""{"type":"navigate","window":"workbench","to":"blade","name":"made_up","by":"agent"}""");

        follower.WaitForAssertion(() => Assert.EndsWith("/scripts?blade=made_up", nav.Uri, StringComparison.Ordinal));
    }

    [Theory]
    [InlineData("", "home")]
    [InlineData("notebooks?path=x.ipynb", "notebooks")]
    [InlineData("scripts", "scripts")]
    [InlineData("grids?grid=g1", "tables")]
    [InlineData("x-scm", "x-scm")]
    public void APageSaysWhichWindowItIs(string address, string kind)
    {
        Assert.Equal(kind, WindowPlace.KindOf(address));
    }

    [Fact]
    public void ThePageSaysItsWindowAsItMoves()
    {
        var nav = Get<NavigationManager>();
        var place = Render<WindowPlace>();
        place.WaitForAssertion(() => Assert.Equal("home", Get<LiveUpdates>().Kind));

        nav.NavigateTo("scripts?new=1");

        place.WaitForAssertion(() => Assert.Equal("scripts", Get<LiveUpdates>().Kind));
    }

    [Fact]
    public void BackIsTheBrowsersOwn()
    {
        JSInterop.Setup<string?>("sab.windowName").SetResult(WhatsNewState.MainWindow);
        var follower = Render<NavigateFollower>();

        Get<LiveUpdates>().Notice("""{"type":"navigate","window":"home","to":"back"}""");

        follower.WaitForAssertion(() => Assert.Equal(-1, JSInterop.VerifyInvoke("sab.historyGo").Arguments[0]));
    }

    [Fact]
    public async Task AWindowPoppedOutStaysWhereItIsAndTheFollowerLetsGoAsync()
    {
        JSInterop.Setup<string?>("sab.windowName").SetResult("sab-notebooks");
        var nav = Get<NavigationManager>();
        var before = nav.Uri;
        var live = Get<LiveUpdates>();
        var subscribers = Subscribers(live, nameof(LiveUpdates.NoticeArrived));
        var follower = Render<NavigateFollower>();

        live.Notice("""{"type":"navigate","window":"home","to":"analyze"}""");

        Assert.Equal(before, nav.Uri);
        Assert.NotNull(follower);
        await DisposeComponentsAsync();
        Assert.Equal(subscribers, Subscribers(live, nameof(LiveUpdates.NoticeArrived)));
    }
}
