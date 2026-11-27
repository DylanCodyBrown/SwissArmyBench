using System.Text.Json;

using Bunit;

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.Extensions.DependencyInjection;

using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.Pages.Workbench;
using SwissArmyBench.Web.Pages.Workbench.Tabs;
using SwissArmyBench.Web.State;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>Review comments on code (the owner, 2026-11-27): the box a comment is typed in, the tab's count, the
/// document's list, and Send to agent: every comment as one send in the document's order, then all cleared; a failed
/// send keeps them. Made-up code only.</summary>
public sealed class ReviewCommentsTests : AppTestContext
{
    private const string Code = "import os\n\ntotal = 0\nfor row in rows:\n    total += row\nprint(total)";

    private readonly CannedServer _server = new();

    public ReviewCommentsTests()
    {
        Services.AddScoped(_ => new HttpClient(_server) { BaseAddress = new Uri("http://127.0.0.1:9/") });
        Services.AddScoped<AgentInboxClient>();
    }

    private static async Task<(ReviewComments Review, ReviewSurfaceStandIn Editor)> TwoCommentsAsync()
    {
        var review = new ReviewComments();
        var editor = new ReviewSurfaceStandIn(Code);
        review.Attach(string.Empty, editor);
        await review.AddAsync(string.Empty, new ReviewPlace(0, 4, 1, 5, 17, "for row in rows:\n    total += row"), "Use sum() here.");
        await review.AddAsync(string.Empty, new ReviewPlace(0, 1, 1, 1, 10, "import os"), " Is this used? ");
        return (review, editor);
    }

    [Fact]
    public async Task Comments_list_in_the_documents_order_and_follow_the_edits_Async()
    {
        var (review, editor) = await TwoCommentsAsync();
        var changes = 0;
        review.Changed += () => changes++;

        Assert.Equal("2 comments", review.CountWords);
        Assert.Equal(["Is this used?", "Use sum() here."], review.Ordered().Select(c => c.Text));
        Assert.Equal(["line 1", "lines 4-5"], review.Ordered().Select(c => c.Where));
        Assert.Equal(2, editor.Drawn.Count);

        editor.Shift = 3; // three lines typed above them: the editor moved both
        await review.RefreshAsync();
        Assert.Equal(["line 4", "lines 7-8"], review.Ordered().Select(c => c.Where));
        Assert.Equal(1, changes);

        await review.RemoveAsync(review.Ordered()[0].Id);
        Assert.Equal("1 comment", review.CountWords);
        Assert.Single(editor.Drawn);
    }

    [Fact]
    public async Task A_notebooks_comments_follow_its_cells_from_the_top_and_the_agents_note_is_marked_Async()
    {
        var review = new ReviewComments();
        review.Attach("cell 7", new ReviewSurfaceStandIn(Code));
        review.Attach("cell 2", new ReviewSurfaceStandIn(Code));
        await review.AddAsync("cell 2", new ReviewPlace(0, 3, 1, 3, 10, "total = 0"), "second");
        var note = await review.AddLinesAsync("cell 7", 4, 5, "first", byAgent: true);

        Assert.Equal(["first", "second"], review.Ordered(["cell 7", "cell 2"]).Select(c => c.Text));
        Assert.True(note.ByAgent);
        Assert.Equal("cell 7, lines 4-5", note.Where);
        Assert.Equal("for row in rows:\n    total += row", note.Code);
        await Assert.ThrowsAsync<InvalidOperationException>(() => review.AddLinesAsync("cell 9", 1, 1, "nowhere", byAgent: true));
    }

    [Fact]
    public void The_box_saves_what_was_typed_and_escape_cancels()
    {
        string? saved = null;
        var cancelled = false;
        var box = Render<ReviewCommentBox>(p => p
            .Add(b => b.Where, "Lines 4-5")
            .Add(b => b.OnSave, EventCallback.Factory.Create<string>(this, text => saved = text))
            .Add(b => b.OnCancel, EventCallback.Factory.Create(this, () => cancelled = true)));

        Assert.Contains("Lines 4-5", box.Find(".review-box-head").TextContent);
        Assert.True(box.Find(".review-box-save").HasAttribute("disabled")); // nothing typed: nothing to save
        Assert.Empty(box.FindAll(".review-box-delete"));

        box.Find("textarea").Input("  Use sum() here.  ");
        box.Find(".review-box").KeyDown(new KeyboardEventArgs { Key = "Enter", CtrlKey = true });
        Assert.Equal("Use sum() here.", saved);

        box.Find(".review-box").KeyDown(new KeyboardEventArgs { Key = "Escape" });
        Assert.True(cancelled);
    }

    [Fact]
    public void A_comment_being_edited_shows_its_words_and_offers_delete()
    {
        var deleted = false;
        var box = Render<ReviewCommentBox>(p => p
            .Add(b => b.Text, "Use sum() here.")
            .Add(b => b.Editing, true)
            .Add(b => b.OnDelete, EventCallback.Factory.Create(this, () => deleted = true)));

        Assert.Equal("Use sum() here.", box.Find("textarea").GetAttribute("value"));
        Assert.Equal("Save", box.Find(".review-box-save").TextContent.Trim());
        box.Find(".review-box-delete").Click();
        Assert.True(deleted);
    }

    [Fact]
    public async Task The_panel_lists_the_comments_and_a_click_goes_to_one_Async()
    {
        var (review, editor) = await TwoCommentsAsync();
        var panel = Render<ReviewPanel>(p => p.Add(r => r.Review, review).Add(r => r.Path, "scripts/load.py"));

        Assert.Equal("2 comments", panel.Find(".review-count").TextContent);
        Assert.Equal(["line 1", "lines 4-5"], panel.FindAll(".review-where").Select(e => e.TextContent));
        Assert.Equal(["Is this used?", "Use sum() here."], panel.FindAll(".review-words").Select(e => e.TextContent));

        panel.FindAll(".review-go")[1].Click();
        Assert.Equal([1], editor.Shown);
        panel.FindAll(".review-edit")[0].Click();
        Assert.Equal([2], editor.Asked);

        panel.FindAll(".review-delete")[0].Click();
        panel.WaitForAssertion(() => Assert.Equal("1 comment", panel.Find(".review-count").TextContent));
    }

    [Fact]
    public void A_document_with_no_comments_shows_no_bar()
    {
        var panel = Render<ReviewPanel>(p => p.Add(r => r.Review, new ReviewComments()).Add(r => r.Path, "scripts/load.py"));

        Assert.Empty(panel.FindAll(".review-panel"));
    }

    [Fact]
    public async Task Send_to_agent_sends_every_comment_once_in_order_and_then_clears_them_Async()
    {
        _server.Answer("POST /agent/inbox/review", "{\"id\": 1, \"waiting\": 1, \"comments\": 2, \"masked\": 0}");
        var (review, editor) = await TwoCommentsAsync();
        var panel = Render<ReviewPanel>(p => p.Add(r => r.Review, review).Add(r => r.Path, "scripts/load.py"));

        panel.Find(".review-send").Click();

        panel.WaitForAssertion(() => Assert.Empty(panel.FindAll(".review-panel")));
        Assert.Equal(0, review.Count);
        Assert.Empty(editor.Drawn); // nothing left drawn on the code
        var (route, body) = Assert.Single(_server.Asked);
        Assert.Equal("POST /agent/inbox/review", route);
        var sent = JsonDocument.Parse(body).RootElement;
        Assert.Equal("scripts/load.py", sent.GetProperty("path").GetString());
        var comments = sent.GetProperty("comments").EnumerateArray().ToList();
        Assert.Equal([1, 4], comments.Select(c => c.GetProperty("line").GetInt32()));
        Assert.Equal([1, 5], comments.Select(c => c.GetProperty("end").GetInt32()));
        Assert.Equal("for row in rows:\n    total += row", comments[1].GetProperty("code").GetString());
        Assert.Equal("Use sum() here.", comments[1].GetProperty("comment").GetString());
        Assert.Equal("user", comments[1].GetProperty("by").GetString());
        Assert.Contains("Sent 2 comments to the agent", Services.GetRequiredService<Notes>().Shown.Single().Words);
    }

    [Fact]
    public async Task A_send_that_fails_keeps_the_comments_and_says_why_Async()
    {
        var (review, editor) = await TwoCommentsAsync(); // the made-up server has no such route: it answers 404
        var panel = Render<ReviewPanel>(p => p.Add(r => r.Review, review).Add(r => r.Path, "scripts/load.py"));

        panel.Find(".review-send").Click();

        panel.WaitForAssertion(() => Assert.Contains("Not sent: Not here. The comments are kept.", panel.Find(".review-error").TextContent));
        Assert.Equal(2, review.Count);
        Assert.Equal(2, editor.Drawn.Count);
        Assert.Equal(2, panel.FindAll(".review-item").Count);
    }

    [Fact]
    public async Task A_tab_shows_how_many_comments_wait_on_it_Async()
    {
        var doc = new OpenDocument(1, notebook: false) { Path = "scripts/load.py" };
        var other = new OpenDocument(2, notebook: false) { Path = "scripts/clean.py" };
        var group = new TabGroup(1);
        group.Tabs.AddRange([1, 2]);
        group.Active = 1;
        doc.Review.Attach(string.Empty, new ReviewSurfaceStandIn(Code));
        await doc.Review.AddLinesAsync(string.Empty, 1, 1, "Is this used?", byAgent: false);
        await doc.Review.AddLinesAsync(string.Empty, 4, 5, "Use sum() here.", byAgent: false);

        var view = Render<GroupView>(p => p
            .Add(g => g.Group, group)
            .Add(g => g.Documents, new Dictionary<int, OpenDocument> { [1] = doc, [2] = other })
            .Add(g => g.Content, _ => _ => { })
            .Add(g => g.Controls, _ => _ => { }));

        var count = Assert.Single(view.FindAll(".wb-tab-comments"));
        Assert.Equal("2", count.TextContent);
        Assert.Equal("2 comments", count.GetAttribute("aria-label"));
    }
}
