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
            {"page": [{"kind": "table", "path": "orders", "id": "", "text": "orders", "link": "[@orders](sab:table/orders)"}],
             "people": [{"name": "Sam Ortiz", "login": "sam-ortiz"}],
             "objects": [{"kind": "cell", "path": "returns.ipynb", "id": "2", "text": "returns.ipynb cell 2", "link": "[@returns.ipynb cell 2](sab:cell/returns.ipynb#2)"}]}
            """);

    public CollaborationTests()
    {
        Services.AddScoped(_ => new HttpClient(_server) { BaseAddress = new Uri("http://127.0.0.1:9/") });
        Services.AddScoped<CollaborationClient>();
        Services.AddScoped<EmojiCatalog>();
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
    public void TheTopIconShowsTheUnreadCountWigglesAsMessagesArriveAndToggles()
    {
        var state = Get<CollaborationState>();
        var button = Render<CollaborationButton>();
        Assert.Empty(button.FindAll(".collab-badge"));
        Assert.Empty(button.FindAll(".wiggle"));
        state.TakeCounts(new CollabUnread(4, 2));
        button.WaitForAssertion(() => Assert.Equal("4", button.Find(".collab-badge").TextContent));
        Assert.NotNull(button.Find(".collab-buddy-face.wiggle"));
        Assert.Contains("2 mentioning you", button.Find("button").GetAttribute("aria-label"));
        Assert.Equal("buddy", button.Find("svg").GetAttribute("data-icon"));
        state.TakeCounts(new CollabUnread(150, 0));
        button.WaitForAssertion(() => Assert.Equal("99+", button.Find(".collab-badge").TextContent));
        button.Find("button").Click();
        Assert.True(state.Open);
    }

    [Fact]
    public void NewsIsSaidOnceInTheCornerAndOpenGoesToTheNewestThread()
    {
        var state = Get<CollaborationState>();
        Get<LiveUpdates>().Notice("""{"type": "collaboration_news", "count": 3, "words": "3 new messages from Sam Ortiz and Avery Lin", "thread": "t-9"}""");
        var note = Assert.Single(Get<Notes>().Shown);
        Assert.Equal("3 new messages from Sam Ortiz and Avery Lin", note.Words);
        Assert.Equal("Open", note.ActionLabel);
        note.Action!();
        Assert.True(state.Open);
        Assert.Equal("t-9", state.OpenThread);
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
        composer.WaitForAssertion(() => Assert.Equal(3, composer.FindAll(".collab-popup li[role=option]").Count));
        var sections = composer.FindAll(".collab-pick-section").Select(s => s.TextContent).ToList();
        Assert.Equal([CollabPicking.OnThisPage, CollabPicking.People, CollabPicking.InTheProject], sections);
        var options = composer.FindAll(".collab-popup li[role=option]").Select(o => o.TextContent).ToList();
        Assert.Contains("orders", options[0]);
        Assert.Contains("Sam Ortiz", options[1]);
        Assert.Contains("returns.ipynb cell 2", options[2]);
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
        panel.WaitForAssertion(() => Assert.Single(panel.FindAll(".collab-timeline > li")));
        Assert.Equal(["All", "Mentions", "This page", "Unresolved"], panel.FindAll(".collab-chip").Select(c => c.TextContent).ToList());
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

    [Fact]
    public void ThePagesObjectsComeFirstInTheAtListAndFilterThisPage()
    {
        var page = Get<PageObjects>();
        var state = Get<CollaborationState>();
        var raised = 0;
        state.Changed += Count;
        page.Set([new CollabReference("notebook", "/home/avery/Returns/returns.ipynb", string.Empty, "returns.ipynb"),
            new CollabReference("cell", "/home/avery/Returns/returns.ipynb", "2", "returns.ipynb cell 2")]);
        page.Set([new CollabReference("notebook", "/home/avery/Returns/returns.ipynb", string.Empty, "returns.ipynb"),
            new CollabReference("cell", "/home/avery/Returns/returns.ipynb", "2", "returns.ipynb cell 2")]);
        Assert.Equal(1, raised); // the same list again changes nothing
        Assert.Equal("[\"/home/avery/Returns/returns.ipynb\"]", state.Page);
        var found = new CollabPicks([new CollabPerson("Sam Ortiz", "sam-ortiz")],
            [new CollabReference("cell", "returns.ipynb", "2", "returns.ipynb cell 2", Link: "[@returns.ipynb cell 2](sab:cell/returns.ipynb#2)"),
             new CollabReference("table", "orders", string.Empty, "orders", Link: "[@orders](sab:table/orders)")]);
        var picks = CollabPicking.Of(page.Objects, found, "cell");
        Assert.Equal(["returns.ipynb cell 2", "Sam Ortiz", "orders"], picks.Select(p => p.Label).ToList());
        Assert.Equal("[@returns.ipynb cell 2](sab:cell//home/avery/Returns/returns.ipynb#2) ", picks[0].Insert);
        page.Clear();
        Assert.Null(state.Page);
        state.Changed -= Count;

        void Count() => raised++;
    }

    [Fact]
    public async Task TheEmojiPickerSearchesEveryEmojiAndRemembersRecentOnesAsync()
    {
        _server.Answer("GET /data/emoji.json", """
            {"format": 1, "unicode": "18.0", "groups": ["Smileys & Emotion", "Activities"], "emoji": [
            ["😀", "grinning face", 0], ["👍", "thumbs up", 0], ["👍🏽", "thumbs up: medium skin tone", 0], ["🎉", "party popper", 1]]}
            """);
        var catalog = Get<EmojiCatalog>();
        Assert.Equal(["🎉"], (await catalog.MatchingAsync("party")).Select(e => e.Emoji).ToList());
        Assert.Equal(["👍", "👍🏽"], (await catalog.MatchingAsync("thumbs")).Select(e => e.Emoji).ToList());
        string? picked = null;
        var picker = Render<EmojiPicker>(p => p.Add(c => c.OnPick, (string e) => picked = e));
        picker.WaitForAssertion(() => Assert.Equal(2, picker.FindAll(".emoji-tab").Count));
        Assert.Equal(["😀", "👍"], picker.FindAll(".emoji-cell").Select(c => c.TextContent).ToList()); // no skin tones in the grid
        picker.Find(".emoji-search").Input("thumbs");
        picker.WaitForAssertion(() => Assert.Equal(2, picker.FindAll(".emoji-cell").Count));
        picker.FindAll(".emoji-cell")[1].Click();
        Assert.Equal("👍🏽", picked);
        Assert.Contains(JSInterop.Invocations, i => i.Identifier == "sab.remember" && i.Arguments[0] as string == "collab.recentEmoji");
    }
}
