using Bunit;

using Microsoft.AspNetCore.Components;
using Microsoft.Extensions.DependencyInjection;

using SwissArmyBench.Web.Api.Collaboration;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.Layout.Collaboration;
using SwissArmyBench.Web.State;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>The Collaboration panel (Layout/Collaboration) over a made-up server: a message's Markdown with its
/// references (a link, or struck through when gone), pictures, tasks and mentions; the state's notices; the status
/// bar's button; the composer's `@` list and Send; the panel's timeline, its team words and a thread opened.
/// Made-up people only.</summary>
public sealed class CollaborationTests : AppTestContext
{
    private const string Timeline = """
        {"project": "/home/avery/Returns", "me": {"name": "Avery Lin", "login": "avery-lin"}, "shared": false,
         "team": {"state": "behind", "words": "2 changes to pull"},
         "channels": [{"name": "general", "key": "#general", "unread": 1}],
         "objects": [], "people": [{"name": "Sam Ortiz", "login": "sam-ortiz"}],
         "unread": {"total": 1, "mentions": 1, "places": {"#general": 1}},
         "items": [
           {"type": "activity", "id": "a1", "time": "2026-11-25T09:00:00Z", "author": {"name": "Sam Ortiz", "login": "sam-ortiz"},
            "object": {"kind": "table", "name": "orders"}, "words": "Added the step 1 filter", "threads": [], "replies": 0},
           {"type": "thread", "id": "t-1", "title": "Returns", "where": "#general", "created": "2026-11-25T09:05:00Z",
            "created_by": {"name": "Sam Ortiz", "login": "sam-ortiz"}, "replies": 0, "last": "2026-11-25T09:05:00Z", "unread": 1,
            "first": {"id": "m1", "thread": "t-1", "kind": "note", "author": {"name": "Sam Ortiz", "login": "sam-ortiz"},
              "time": "2026-11-25T09:05:00Z", "edited": "", "deleted": false, "body": "@avery-lin returns look high",
              "mentions": ["avery-lin"], "references": [], "reactions": [], "mine": false}}
         ]}
        """;

    private const string Thread = """
        {"type": "thread", "id": "t-1", "title": "Returns", "where": "#general", "replies": 0, "unread": 0, "pinned": false,
         "messages": [{"id": "m1", "thread": "t-1", "kind": "note", "author": {"name": "Sam Ortiz", "login": "sam-ortiz"},
           "time": "2026-11-25T09:05:00Z", "edited": "", "deleted": false, "body": "See [@returns.ipynb cell 2](sab:cell/returns.ipynb#2)",
           "mentions": [], "reactions": [{"emoji": "👍", "people": ["avery-lin"], "mine": true}], "mine": false,
           "references": [{"kind": "cell", "path": "returns.ipynb", "id": "2", "text": "returns.ipynb cell 2", "gone": false,
             "href": "notebooks?path=%2Fhome%2Favery%2FReturns%2Freturns.ipynb&cell=2"}]}]}
        """;

    private readonly CannedServer _server = new CannedServer()
        .Answer("GET /collaboration", Timeline)
        .Answer("GET /collaboration/thread", Thread)
        .Answer("POST /collaboration/resolve", Thread.Replace("\"pinned\": false", "\"pinned\": false, \"resolved\": {\"by\": \"avery-lin\", \"time\": \"2026-11-25T09:10:00Z\"}"))
        .Answer("GET /collaboration/unread", """{"total": 1, "mentions": 1}""")
        .Answer("GET /collaboration/objects", """
            {"people": [{"name": "Sam Ortiz", "login": "sam-ortiz"}],
             "objects": [{"kind": "cell", "path": "returns.ipynb", "id": "2", "text": "returns.ipynb cell 2", "link": "[@returns.ipynb cell 2](sab:cell/returns.ipynb#2)"}]}
            """);

    public CollaborationTests()
    {
        Services.AddScoped(_ => new HttpClient(_server) { BaseAddress = new Uri("http://127.0.0.1:9/") });
        Services.AddScoped<CollaborationClient>();
    }

    private static CollabMessage Message(string body, IReadOnlyList<CollabReference>? references = null, IReadOnlyList<string>? mentions = null) =>
        new("m1", "t-1", "note", new("Avery Lin", "avery-lin"), "2026-11-25T09:00:00Z", string.Empty, false, body,
            mentions ?? [], references ?? [], [], true);

    [Fact]
    public void AReferenceIsALinkToItsObjectOrStruckThroughWhenGone()
    {
        var there = new CollabReference("table", "orders", string.Empty, "orders", Href: "tables?table=orders");
        var html = CollabWords.Body(Message("Look at [@orders](sab:table/orders) and [@old](sab:table/old)", [there, new("table", "old", string.Empty, "old", Gone: true)]));
        Assert.Contains("<a class=\"collab-ref\" data-kind=\"table\" href=\"tables?table=orders\"", html);
        Assert.Contains("<s>@old</s>", html);
        Assert.Contains(CollabWords.GoneWords, html);
    }

    [Fact]
    public void PicturesTasksStrikeCodeAndMentionsAreDrawn()
    {
        var html = CollabWords.Body(Message(
            "@sam-ortiz ~~old~~ ![chart](sab-image:ab12-1.png)\n\n- [x] done\n- [ ] to do\n\n```sql\nSELECT @sam-ortiz\n```",
            mentions: ["sam-ortiz"]));
        Assert.Contains("<span class=\"collab-mention\">@sam-ortiz</span>", html);
        Assert.Contains("<del>old</del>", html);
        Assert.Contains("src=\"/collaboration/image?thread=t-1&amp;name=ab12-1.png\"", html);
        Assert.Contains("type=\"checkbox\" disabled checked", html);
        Assert.Contains("<code data-lang=\"sql\">SELECT @sam-ortiz</code>", html); // code is never a mention
    }

    [Fact]
    public void ScriptsInAMessageStayText()
    {
        var html = CollabWords.Body(Message("<script>alert(1)</script> [@x\"><b>](sab:table/x)"));
        Assert.DoesNotContain("<script>", html);
        Assert.DoesNotContain("<b>", html);
    }

    [Fact]
    public void TheNoticesOpenThePanelAndCountUnreadAndItLetsGo()
    {
        var state = Get<CollaborationState>();
        var live = Get<LiveUpdates>();
        var listening = Subscribers(live, "NoticeArrived");
        Assert.True(listening >= 1);
        live.Notice("""{"type": "collaboration_unread", "total": 3, "mentions": 1}""");
        Assert.Equal((3, 1), (state.Unread, state.Mentions));
        live.Notice("""{"type": "collaboration_show", "where": "table:orders", "anchor": {"kind": "table", "path": "orders", "id": "", "text": "orders"}}""");
        Assert.True(state.Open);
        Assert.Equal("table:orders", state.Where);
        Assert.Equal("orders", state.Anchor?.Text);
        var version = state.Version;
        live.Notice("""{"type": "collaboration_changed", "threads": ["t-1"]}""");
        Assert.Equal(version + 1, state.Version);
        state.Dispose();
        Assert.Equal(listening - 1, Subscribers(live, "NoticeArrived"));
    }

    [Fact]
    public void TheStatusBarButtonShowsTheUnreadCountAndToggles()
    {
        var state = Get<CollaborationState>();
        var button = Render<CollaborationButton>();
        Assert.Empty(button.FindAll(".collab-badge"));
        state.TakeCounts(new CollabUnread(4, 2));
        button.WaitForAssertion(() => Assert.Equal("4", button.Find(".collab-badge").TextContent));
        Assert.Contains("2 mentioning you", button.Find("button").GetAttribute("aria-label"));
        button.Find("button").Click();
        Assert.True(state.Open);
    }

    [Fact]
    public async Task TheComposerListsObjectsAfterAnAtAndSendsAsync()
    {
        string? sent = null;
        Func<string, IReadOnlyList<CollabImage>, Task<bool>> send = (body, _) =>
        {
            sent = body;
            return Task.FromResult(true);
        };
        var composer = Render<CollabComposer>(p => p.Add(c => c.OnSend, send));
        await composer.InvokeAsync(() => composer.Instance.TypedAsync("check @ret", 10));
        composer.WaitForAssertion(() => Assert.Equal(2, composer.FindAll(".collab-popup li").Count));
        Assert.Contains("returns.ipynb cell 2", composer.Find(".collab-popup").TextContent);
        await composer.InvokeAsync(() => composer.Instance.PopupKeyAsync("Escape"));
        Assert.Empty(composer.FindAll(".collab-popup"));
        await composer.InvokeAsync(() => composer.Instance.TypedAsync("All **good**", 12));
        await composer.InvokeAsync(() => composer.Instance.SendFromKeyAsync());
        Assert.Equal("All **good**", sent);
    }

    [Fact]
    public void ThePanelDrawsTheTimelineTheTeamWordsAndOpensAThread()
    {
        var panel = Render<CollaborationPanel>(p => p.Add(c => c.Kind, "tables"));
        panel.WaitForAssertion(() => Assert.Equal(2, panel.FindAll(".collab-timeline > li").Count));
        Assert.Contains("Added the step 1 filter", panel.Find(".collab-item.activity").TextContent);
        Assert.Contains("@avery-lin", panel.Find(".collab-mention").TextContent);
        Assert.Contains("not shared with your team", panel.Find(".collab-line").TextContent);
        Assert.Contains("Pull to see the team's latest", panel.Find(".collab-line.team").TextContent);
        Assert.Equal(1, Get<CollaborationState>().Unread);

        panel.Find(".collab-thread-open").Click();
        panel.WaitForAssertion(() => Assert.NotNull(panel.Find(".collab-thread")));
        Assert.Equal("Returns", panel.Find(".collab-title").TextContent);
        Assert.Equal("notebooks?path=%2Fhome%2Favery%2FReturns%2Freturns.ipynb&cell=2", panel.Find("a.collab-ref").GetAttribute("href"));
        Assert.Contains("1", panel.Find(".collab-reaction.mine").TextContent);
        panel.FindAll("button").First(b => b.TextContent.Contains("Resolve", StringComparison.Ordinal)).Click();
        panel.WaitForAssertion(() => Assert.Contains("Resolved by avery-lin", panel.Find(".collab-resolved-line").TextContent));
        Assert.Contains(_server.Asked, a => a.Route == "POST /collaboration/resolve" && a.Body.Contains("\"resolved\":true", StringComparison.Ordinal));
    }

    [Fact]
    public void CollaborateOnAnObjectOpensThePanelThere()
    {
        var state = Get<CollaborationState>();
        var entry = state.Entry(CollaborationState.FileAnchor("/home/avery/Returns/load.sql"));
        Assert.Equal(CollaborationState.CollaborateWords, entry.Label);
        entry.Run();
        Assert.True(state.Open);
        Assert.Equal("sql:/home/avery/Returns/load.sql", state.Where);
        Assert.Equal("load.sql", state.Anchor?.Text);
        var button = Render<CollaborateButton>(p => p.Add(c => c.Anchor, new CollabReference("connection", "Finance", string.Empty, "Finance")));
        button.Find("button").Click();
        Assert.Equal("connection:Finance", state.Where);
        _ = Get<NavigationManager>();
    }
}
