using System.Text.Json;

using Bunit;

using Microsoft.AspNetCore.Components.Web;
using Microsoft.Extensions.DependencyInjection;

using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.Pages.Workbench;
using SwissArmyBench.Web.Pages.Workbench.Docs;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>A text document's tab (the owner, 2026-11-27: "Our markdown reader and inline editor would be a great
/// addition" / "html, markdown, and renderable code should get a preview toggle"): which files have which preview,
/// the one toggle, the Markdown reader's blocks (a click edits one in place, written back by the server's rule; a
/// task box ticks), the three views, and the renderer's nested lists, live task boxes, pictures and file links.</summary>
public sealed class TextDocumentTests : AppTestContext
{
    private const string Blocks = """
        {"text": "# Notes\n\nA first paragraph.\n\n- [ ] Check\n- [x] Done\n\n```mermaid\nflowchart TD\n    a --> b\n```\n", "changed": false, "blocks": [
          {"index": 0, "kind": "heading", "line": 1, "lines": 1, "text": "# Notes", "language": "", "tasks": 0},
          {"index": 1, "kind": "paragraph", "line": 3, "lines": 1, "text": "A first paragraph.", "language": "", "tasks": 0},
          {"index": 2, "kind": "list", "line": 5, "lines": 2, "text": "- [ ] Check\n- [x] Done", "language": "", "tasks": 2},
          {"index": 3, "kind": "diagram", "line": 8, "lines": 4, "text": "```mermaid\nflowchart TD\n    a --> b\n```", "language": "mermaid", "tasks": 0}
        ]}
        """;

    private const string Text = "# Notes\n\nA first paragraph.\n\n- [ ] Check\n- [x] Done\n\n```mermaid\nflowchart TD\n    a --> b\n```\n";

    private readonly CannedServer _server = new();

    public TextDocumentTests()
    {
        Services.AddScoped(_ => new HttpClient(_server) { BaseAddress = new Uri("http://127.0.0.1:9/") });
        Services.AddScoped<WorkbenchClient>();
        Services.AddScoped<AgentInboxClient>();
        _server.Answer("POST /workbench/markdown", Blocks);
    }

    [Theory]
    [InlineData("/p/README.md", "markdown", "markdown", "preview")]
    [InlineData("/p/docs/page.HTML", "html", "html", "source")]
    [InlineData("/p/logo.svg", "xml", "svg", "source")]
    [InlineData("/p/flow.mmd", "plaintext", "mermaid", "source")]
    [InlineData("/p/flow.mermaid", "plaintext", "mermaid", "source")]
    [InlineData("/p/sales.vl.json", "json", "vega", "source")]
    [InlineData("/p/todo.txt", "plaintext", "", "source")]
    public void Each_kind_of_text_document_has_its_language_its_preview_and_its_first_view(string path, string language, string preview, string first)
    {
        var kind = TextFiles.KindOf(path);
        Assert.NotNull(kind);
        Assert.Equal((language, preview, first), (kind.Language, kind.Preview, kind.First));
        Assert.Equal(preview.Length > 0, kind.HasPreview);
        var doc = new OpenDocument(1, false) { Path = path };
        Assert.True(doc.IsText);
        Assert.Equal(first, doc.TextViewNow);
        doc.TextViewChosen = TextFiles.Split; // the tab remembers the view chosen on its bar
        Assert.Equal("split", doc.TextViewNow);
    }

    [Fact]
    public void A_plain_json_file_and_a_script_are_not_text_documents()
    {
        Assert.Null(TextFiles.KindOf("/p/data.json"));
        Assert.Null(TextFiles.KindOf("/p/load.py"));
        Assert.Null(TextFiles.KindOf("/p/.hidden.md"));
        Assert.Null(TextFiles.KindOf(null));
    }

    [Fact]
    public void The_one_toggle_has_the_same_three_choices_and_says_Read_for_markdown()
    {
        string? chosen = null;
        var toggle = Render<PreviewToggle>(p => p.Add(t => t.View, "preview").Add(t => t.Preview, "markdown").Add(t => t.OnView, v => chosen = v));
        var buttons = toggle.FindAll("button");
        Assert.Equal(["Read", "Split", "Source"], buttons.Select(b => b.TextContent));
        Assert.Equal(["true", "false", "false"], buttons.Select(b => b.GetAttribute("aria-pressed")));
        buttons[1].Click();
        Assert.Equal("split", chosen);

        var html = Render<PreviewToggle>(p => p.Add(t => t.View, "source").Add(t => t.Preview, "html"));
        Assert.Equal(["Preview", "Split", "Source"], html.FindAll("button").Select(b => b.TextContent));
        Assert.Equal("true", html.Find(".wb-view-source").GetAttribute("aria-pressed"));
    }

    [Fact]
    public void The_reader_draws_the_servers_blocks_each_its_own_box()
    {
        var reader = Render<MarkdownReader>(p => p.Add(r => r.Text, Text).Add(r => r.Path, "/p/notes.md").Add(r => r.Editable, true));
        reader.WaitForAssertion(() => Assert.Equal(4, reader.FindAll(".md-block").Count));
        Assert.Equal("true", reader.Find(".md-reader").GetAttribute("data-editable"));
        Assert.Equal("<h1>Notes</h1>", reader.Find("[data-block='0'] .note-body").InnerHtml);
        Assert.Equal("A first paragraph.", reader.Find("[data-block='1'] p").TextContent);
        // The task boxes are live, numbered within their block; the file says which are ticked.
        var boxes = reader.FindAll("[data-block='2'] input[type=checkbox]");
        Assert.Equal(["0", "1"], boxes.Select(b => b.GetAttribute("data-task")));
        Assert.False(boxes[0].HasAttribute("disabled"));
        Assert.False(boxes[0].HasAttribute("checked"));
        Assert.True(boxes[1].HasAttribute("checked"));
        // A ```mermaid block is its diagram, not its code.
        Assert.Single(reader.FindAll("[data-block='3'] .wb-diagram"));
        Assert.Empty(reader.FindAll("[data-block='3'] pre"));
        using var asked = JsonDocument.Parse(_server.Asked[0].Body);
        Assert.Equal(Text, asked.RootElement.GetProperty("text").GetString());
    }

    [Fact]
    public async Task A_block_clicked_becomes_its_source_and_Escape_writes_only_that_block_backAsync()
    {
        string? edited = null;
        var reader = Render<MarkdownReader>(p => p.Add(r => r.Text, Text).Add(r => r.Editable, true).Add(r => r.OnEdited, t => edited = t));
        reader.WaitForAssertion(() => Assert.Equal(4, reader.FindAll(".md-block").Count));

        await reader.InvokeAsync(() => reader.Instance.Edit(1)); // the page's own click (interop/documents.js reader)
        var box = reader.Find("[data-block='1'] textarea.md-block-edit");
        Assert.Equal("A first paragraph.", box.GetAttribute("value"));
        Assert.Equal(1, reader.Instance.Editing);
        Assert.Single(reader.FindAll("textarea")); // one block at a time; the others stay drawn
        Assert.Equal("<h1>Notes</h1>", reader.Find("[data-block='0'] .note-body").InnerHtml);

        var after = Text.Replace("A first paragraph.", "A better paragraph.", StringComparison.Ordinal);
        _server.Answer("POST /workbench/markdown", Blocks.Replace("A first paragraph.", "A better paragraph.", StringComparison.Ordinal).Replace("\"changed\": false", "\"changed\": true", StringComparison.Ordinal));
        box.Input("A better paragraph.");
        await box.KeyDownAsync(new KeyboardEventArgs { Key = "Escape" });

        reader.WaitForAssertion(() => Assert.Equal(after, edited));
        Assert.Empty(reader.FindAll("textarea")); // drawn again
        Assert.Equal("A better paragraph.", reader.Find("[data-block='1'] p").TextContent);
        using var sent = JsonDocument.Parse(_server.Asked[^1].Body);
        Assert.Equal(1, sent.RootElement.GetProperty("block").GetInt32());
        Assert.Equal("A better paragraph.", sent.RootElement.GetProperty("to").GetString());
        Assert.Equal(Text, sent.RootElement.GetProperty("text").GetString()); // the server splices it into the file
    }

    [Fact]
    public async Task Escape_with_nothing_changed_writes_nothing_and_a_view_that_only_shows_edits_nothingAsync()
    {
        var edits = 0;
        var reader = Render<MarkdownReader>(p => p.Add(r => r.Text, Text).Add(r => r.Editable, true).Add(r => r.OnEdited, _ => edits++));
        reader.WaitForAssertion(() => Assert.Equal(4, reader.FindAll(".md-block").Count));
        await reader.InvokeAsync(() => reader.Instance.Edit(0));
        var asked = _server.Asked.Count;
        await reader.Find("textarea").KeyDownAsync(new KeyboardEventArgs { Key = "Escape" });
        Assert.Empty(reader.FindAll("textarea"));
        Assert.Equal((0, asked), (edits, _server.Asked.Count));

        var shown = Render<MarkdownReader>(p => p.Add(r => r.Text, Text).Add(r => r.Editable, false)); // Split view's preview
        shown.WaitForAssertion(() => Assert.Equal(4, shown.FindAll(".md-block").Count));
        await shown.InvokeAsync(() => shown.Instance.Edit(1));
        Assert.Empty(shown.FindAll("textarea"));
        Assert.All(shown.FindAll(".md-block"), block => Assert.False(block.HasAttribute("tabindex")));
    }

    [Fact]
    public async Task A_task_box_ticked_is_sent_by_its_block_and_numberAsync()
    {
        string? edited = null;
        var reader = Render<MarkdownReader>(p => p.Add(r => r.Text, Text).Add(r => r.Editable, true).Add(r => r.OnEdited, t => edited = t));
        reader.WaitForAssertion(() => Assert.Equal(4, reader.FindAll(".md-block").Count));
        var after = Text.Replace("- [ ] Check", "- [x] Check", StringComparison.Ordinal);
        _server.Answer("POST /workbench/markdown", Blocks.Replace("- [ ] Check", "- [x] Check", StringComparison.Ordinal).Replace("\"changed\": false", "\"changed\": true", StringComparison.Ordinal));

        await reader.InvokeAsync(() => reader.Instance.Tick(2, 0));

        reader.WaitForAssertion(() => Assert.Equal(after, edited));
        using var sent = JsonDocument.Parse(_server.Asked[^1].Body);
        Assert.Equal((2, 0), (sent.RootElement.GetProperty("block").GetInt32(), sent.RootElement.GetProperty("task").GetInt32()));
        Assert.All(reader.FindAll("[data-block='2'] input"), box => Assert.True(box.HasAttribute("checked")));
    }

    [Fact]
    public void The_three_views_draw_the_source_the_preview_or_both()
    {
        var read = Render<TextFileView>(p => p.Add(v => v.Text, Text).Add(v => v.Path, "/p/notes.md").Add(v => v.View, "preview"));
        Assert.Equal("preview", read.Find(".wb-textfile").GetAttribute("data-view"));
        Assert.Empty(read.FindAll(".wb-text-source"));
        Assert.Equal("true", read.Find(".md-reader").GetAttribute("data-editable")); // Read: a click edits a block

        var split = Render<TextFileView>(p => p.Add(v => v.Text, Text).Add(v => v.Path, "/p/notes.md").Add(v => v.View, "split"));
        Assert.Single(split.FindAll(".wb-text-source"));
        Assert.Equal("false", split.Find(".md-reader").GetAttribute("data-editable")); // its source is beside it

        var source = Render<TextFileView>(p => p.Add(v => v.Text, Text).Add(v => v.Path, "/p/notes.md").Add(v => v.View, "source"));
        Assert.Single(source.FindAll(".wb-text-source"));
        Assert.Empty(source.FindAll(".wb-text-preview"));
    }

    [Fact]
    public void An_html_page_and_an_svg_picture_are_drawn_in_the_walled_off_frame_never_in_the_page()
    {
        const string Page = "<!doctype html><html><body><h1 id=\"made-up\">Hello</h1><script>parent.document.title = 'reached'</script><img src=\"logo.png\"></body></html>";
        var html = Render<TextFileView>(p => p.Add(v => v.Text, Page).Add(v => v.Path, "/p/page.html").Add(v => v.View, "preview"));
        Assert.Equal("true", html.Find(".wb-preview-stage").GetAttribute("data-framed"));
        Assert.Empty(html.FindAll("#made-up")); // its markup is never part of the app's page
        Assert.DoesNotContain("<script>", html.Markup, StringComparison.Ordinal);
        Assert.Contains("loads nothing from this computer or the network", html.Find(".wb-preview-note").TextContent, StringComparison.Ordinal);

        const string Svg = "<svg xmlns=\"http://www.w3.org/2000/svg\"><script>alert(1)</script><rect width=\"4\" height=\"4\"/></svg>";
        var picture = Render<TextFileView>(p => p.Add(v => v.Text, Svg).Add(v => v.Path, "/p/logo.svg").Add(v => v.View, "split"));
        Assert.Single(picture.FindAll(".wb-preview-stage"));
        Assert.Empty(picture.FindAll(".wb-text-preview svg"));
        // The frame's page shows the SVG as a picture of its bytes: nothing in it runs.
        var framed = PictureFrame.Of(Svg, dark: false);
        Assert.Contains("<img alt=\"The picture\" src=\"data:image/svg+xml;base64,", framed, StringComparison.Ordinal);
        Assert.DoesNotContain("<script>", framed, StringComparison.Ordinal);
    }

    [Fact]
    public void A_diagram_a_chart_spec_and_plain_text()
    {
        var diagram = Render<TextFileView>(p => p.Add(v => v.Text, "flowchart TD\n    a --> b\n").Add(v => v.Path, "/p/flow.mmd").Add(v => v.View, "split"));
        Assert.Single(diagram.FindAll(".wb-text-preview .wb-diagram"));

        var broken = Render<TextFileView>(p => p.Add(v => v.Text, "{ not json").Add(v => v.Path, "/p/sales.vl.json").Add(v => v.View, "preview"));
        Assert.Contains("Line 1: the spec is not JSON yet", broken.Find(".wb-preview-error").TextContent, StringComparison.Ordinal);
        var chart = Render<TextFileView>(p => p.Add(v => v.Text, "{\"mark\": \"bar\"}").Add(v => v.Path, "/p/sales.vl.json").Add(v => v.View, "preview"));
        Assert.Single(chart.FindAll(".vega-host"));

        // Plain text has no preview: whatever view is asked, its source.
        var plain = Render<TextFileView>(p => p.Add(v => v.Text, "to do").Add(v => v.Path, "/p/todo.txt").Add(v => v.View, "preview"));
        Assert.Equal("source", plain.Find(".wb-textfile").GetAttribute("data-view"));
        Assert.Empty(plain.FindAll(".wb-text-preview"));
    }

    [Fact]
    public void Lists_nest_by_their_indent()
    {
        var html = MarkdownText.ToHtml("- one\n  - inner a\n  - inner b\n    1. deep\n- two\n\nafter");
        Assert.Contains("<ul><li>one<ul><li>inner a</li><li>inner b<ol><li>deep</li></ol></li></ul></li><li>two</li></ul><p>after</p>", html, StringComparison.Ordinal);
        // A flat list is as it always was.
        Assert.Contains("<ul><li>one</li><li>two</li></ul>", MarkdownText.ToHtml("- one\n- two"), StringComparison.Ordinal);
        Assert.Contains("<ul><li>a</li></ul><ol><li>b</li></ol>", MarkdownText.ToHtml("- a\n1. b"), StringComparison.Ordinal);
    }

    [Fact]
    public void Task_boxes_are_live_only_for_a_file_and_pictures_and_file_links_only_through_the_reader()
    {
        // Anywhere else (a notebook's cell, a note) a task box only shows, and a relative address stays words.
        var plain = MarkdownText.ToHtml("- [ ] todo\n\n![logo](docs/logo.svg) and [the plan](docs/plan.md)");
        Assert.Contains("<input type=\"checkbox\" disabled aria-label=\"To do\">", plain, StringComparison.Ordinal);
        Assert.DoesNotContain("<img", plain, StringComparison.Ordinal);
        Assert.Contains("![logo](docs/logo.svg)", plain, StringComparison.Ordinal);
        Assert.Contains("[the plan](docs/plan.md)", plain, StringComparison.Ordinal);

        var options = new MarkdownOptions(Tasks: true, Image: (alt, address) => $"<img alt=\"{alt}\" data-at=\"{address}\">", Link: (inner, address) => $"<a data-file href=\"{address}\">{inner}</a>");
        var file = MarkdownText.ToHtml("- [ ] todo\n- [x] done\n\n![logo](docs/logo.svg) and [the **plan**](docs/plan.md) and [web](https://example.com)", null, options);
        Assert.Contains("<input type=\"checkbox\" data-task=\"0\" aria-label=\"To do\">", file, StringComparison.Ordinal);
        Assert.Contains("<input type=\"checkbox\" data-task=\"1\" checked aria-label=\"Done\">", file, StringComparison.Ordinal);
        Assert.Contains("<img alt=\"logo\" data-at=\"docs/logo.svg\">", file, StringComparison.Ordinal);
        Assert.Contains("<a data-file href=\"docs/plan.md\">the <strong>plan</strong></a>", file, StringComparison.Ordinal);
        Assert.Contains("href=\"https://example.com\" target=\"_blank\"", file, StringComparison.Ordinal);
        // What a file says never becomes markup, through the reader either.
        Assert.DoesNotContain("<script>", MarkdownText.ToHtml("![x](a.png)<script>alert(1)</script>", null, options), StringComparison.Ordinal);
    }
}
