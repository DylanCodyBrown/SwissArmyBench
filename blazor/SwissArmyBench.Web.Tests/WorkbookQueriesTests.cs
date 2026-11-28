using System.Text.Json;

using Bunit;

using Microsoft.Extensions.DependencyInjection;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Pages.Grids;
using SwissArmyBench.Web.Pages.Workbench;
using SwissArmyBench.Web.Pages.Workbench.Ide;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>Workbook queries (the owner, 2026-11-28: "Excel's own Power Query"): a Power Query file linked to an Excel
/// workbook shows "Saves into &lt;workbook&gt;" over its editor, what stands in a save's way in one sentence each
/// (Reload and Keep mine for queries changed on disk), a save's queries in its Output, and the New file dialog
/// filled in with the workbook a table's tab asked for.</summary>
public sealed class WorkbookQueriesTests : AppTestContext
{
    private const string Linked = "// workbook: Sales Report.xlsx\n\nsection Section1;\n\nshared Sales = 1;\n";

    private readonly CannedServer _server = new();

    public WorkbookQueriesTests()
    {
        Services.AddScoped(_ => new HttpClient(_server) { BaseAddress = new Uri("http://127.0.0.1:9/") });
        Services.AddScoped<ApiClient>();
        Services.AddScoped<ScriptIdeClient>();
    }

    [Fact]
    public void The_line_says_which_workbook_the_file_saves_into()
    {
        var line = Render<WorkbookLinkLine>(p => p.Add(l => l.Link, new WorkbookLink(true, "Sales Report.xlsx", "/made/up/Sales Report.xlsx", true, 3)));
        Assert.Equal("Saves into Sales Report.xlsx", line.Find(".wb-pq-saves-into").TextContent);
        Assert.Equal("/made/up/Sales Report.xlsx", line.Find(".wb-pq-saves-into strong").GetAttribute("title"));
        Assert.Contains("3 workbook queries", line.Markup, StringComparison.Ordinal);
        Assert.DoesNotContain("blocked", line.Find(".wb-pq-workbook").ClassName, StringComparison.Ordinal);
        Assert.Empty(line.FindAll(".wb-pq-reload"));
        Assert.Single(line.FindAll(".wb-pq-preview-save"));
    }

    [Fact]
    public void Queries_changed_on_disk_offer_reload_and_keep_mine()
    {
        var asked = new List<string>();
        var line = Render<WorkbookLinkLine>(p => p
            .Add(l => l.Link, new WorkbookLink(true, "Sales Report.xlsx", "/made/up/Sales Report.xlsx", true, 3, OpenInExcel: true, Changed: true))
            .Add(l => l.OnReload, () => asked.Add("reload"))
            .Add(l => l.OnKeepMine, () => asked.Add("keep")));
        Assert.Contains("blocked", line.Find(".wb-pq-workbook").ClassName, StringComparison.Ordinal);
        Assert.Contains("Open in Excel. Close it in Excel first.", line.Markup, StringComparison.Ordinal);
        Assert.Contains("Its queries changed on disk since this file was opened.", line.Markup, StringComparison.Ordinal);
        line.Find(".wb-pq-reload").Click();
        line.Find(".wb-pq-keep-mine").Click();
        Assert.Equal(["reload", "keep"], asked);
    }

    [Fact]
    public void A_workbook_that_cannot_be_saved_into_says_why_and_offers_no_preview()
    {
        var link = new WorkbookLink(true, "old.xls", "/made/up/old.xls", true, 0, Why: "old.xls is an older .xls workbook: save it as .xlsx in Excel to edit its queries here.");
        var line = Render<WorkbookLinkLine>(p => p.Add(l => l.Link, link));
        Assert.Contains("older .xls workbook", line.Find(".wb-pq-workbook-why").TextContent, StringComparison.Ordinal);
        Assert.Empty(line.FindAll(".wb-pq-preview-save"));
    }

    [Fact]
    public async Task A_linked_files_tab_shows_its_workbook_and_its_saves_queriesAsync()
    {
        _server.Answer("POST /scripts/pq/workbook", """{"linked": true, "workbook": "Sales Report.xlsx", "workbook_path": "/made/up/Sales Report.xlsx", "there": true, "queries": 3, "open_in_excel": false, "changed": false, "why": null}""");
        _server.Answer("POST /scripts/pq/workbook/save", """
            {"workbook": "Sales Report.xlsx", "written": true, "writes": true, "backup": "/made/up/Sales Report.backup.xlsx",
             "words": "Saved into Sales Report.xlsx: 1 changed. Excel runs them on its next Refresh.",
             "changes": [{"query": "Sales", "what": "changed", "words": "Changed: Excel runs it again on Refresh."},
                         {"query": "Threshold", "what": "same", "words": "The same."}]}
            """);
        var view = Render<PowerQueryFileView>(p => p.Add(v => v.Text, Linked).Add(v => v.Path, "/made/up/report.pq"));
        view.WaitForElement(".wb-pq-workbook");
        Assert.Equal("Saves into Sales Report.xlsx", view.Find(".wb-pq-saves-into").TextContent);
        Assert.Equal("Sales Report.xlsx", view.Instance.Workbook);

        var words = await view.InvokeAsync(view.Instance.SaveIntoWorkbookAsync);
        Assert.Equal("Saved into Sales Report.xlsx: 1 changed. Excel runs them on its next Refresh.", words);
        view.WaitForElement(".wb-pq-change");
        Assert.Equal("Saved into the workbook", view.Find(".wb-console-head strong").TextContent);
        Assert.Equal(["Sales", "Threshold"], view.FindAll(".wb-pq-change strong").Select(e => e.TextContent));
        Assert.Contains("/made/up/Sales Report.backup.xlsx", view.Find(".wb-pq-backup").TextContent, StringComparison.Ordinal);
        var sent = JsonDocument.Parse(_server.Asked.Last(a => a.Route == "POST /scripts/pq/workbook/save").Body).RootElement;
        Assert.Equal("/made/up/report.pq", sent.GetProperty("path").GetString());
        Assert.False(sent.GetProperty("force").GetBoolean());
    }

    [Fact]
    public void A_workbook_with_no_power_query_offers_to_add_it_and_still_previews()
    {
        var asked = new List<string>();
        var link = new WorkbookLink(true, "plain.xlsx", "/made/up/plain.xlsx", true, 0, Why: "plain.xlsx has no Power Query yet.", CanAdd: true);
        var line = Render<WorkbookLinkLine>(p => p.Add(l => l.Link, link).Add(l => l.OnAddPowerQuery, () => asked.Add("add")));
        Assert.Contains("no Power Query yet", line.Find(".wb-pq-workbook-why").TextContent, StringComparison.Ordinal);
        Assert.Equal("Add Power Query to this workbook", line.Find(".wb-pq-add-power-query").TextContent);
        Assert.Single(line.FindAll(".wb-pq-preview-save"));
        line.Find(".wb-pq-add-power-query").Click();
        Assert.Equal(["add"], asked);

        var open = Render<WorkbookLinkLine>(p => p.Add(l => l.Link, link with { OpenInExcel = true }));
        Assert.True(open.Find(".wb-pq-add-power-query").HasAttribute("disabled"));
    }

    [Fact]
    public async Task A_save_never_adds_power_query_and_the_button_does_and_says_what_was_addedAsync()
    {
        const string NoQueries = """{"linked": true, "workbook": "plain.xlsx", "workbook_path": "/made/up/plain.xlsx", "there": true, "queries": 0, "open_in_excel": false, "changed": false, "why": "plain.xlsx has no Power Query yet.", "can_add": true}""";
        const string Stopped = "plain.xlsx has no Power Query yet. Add Power Query to this workbook to save these queries into it.";
        const string Added = "Added Power Query to plain.xlsx: 1 query, connection only (no sheet, no table).";
        _server.Answer("POST /scripts/pq/workbook", NoQueries);
        _server.Refuse("POST /scripts/pq/workbook/save", $$"""{"error": "{{Stopped}}", "needs_add": true}""");
        var said = new List<string>();
        var view = Render<PowerQueryFileView>(p => p
            .Add(v => v.Text, Linked.Replace("Sales Report.xlsx", "plain.xlsx", StringComparison.Ordinal))
            .Add(v => v.Path, "/made/up/plain.pq")
            .Add(v => v.OnSaid, said.Add));
        view.WaitForElement(".wb-pq-add-power-query");

        // The page's Save: stopped, with the offer beside the reason. Nothing asked for the add.
        Assert.Null(await view.InvokeAsync(view.Instance.SaveIntoWorkbookAsync));
        view.WaitForElement(".wb-sql-error .wb-pq-add-power-query");
        Assert.Contains(Stopped, view.Find(".wb-sql-error").TextContent, StringComparison.Ordinal);
        var plain = JsonDocument.Parse(_server.Asked.Last(a => a.Route == "POST /scripts/pq/workbook/save").Body).RootElement;
        Assert.False(plain.GetProperty("add").GetBoolean());

        // The user's own click: add is sent, and what was added is said.
        _server.Answer("POST /scripts/pq/workbook/save", $$"""
            {"workbook": "plain.xlsx", "written": true, "writes": true, "backup": "/made/up/plain.backup.xlsx",
             "adds_power_query": true, "new_parts": ["customXml/item1.xml", "customXml/itemProps1.xml"], "words": "{{Added}}",
             "changes": [{"query": "Sales", "what": "added", "words": "Added as connection only (no sheet)."}]}
            """);
        _server.Answer("POST /scripts/pq/workbook", NoQueries.Replace("\"queries\": 0", "\"queries\": 1", StringComparison.Ordinal).Replace("\"can_add\": true", "\"can_add\": false", StringComparison.Ordinal).Replace("\"plain.xlsx has no Power Query yet.\"", "null", StringComparison.Ordinal));
        await view.Find(".wb-sql-error .wb-pq-add-power-query").ClickAsync(new());
        view.WaitForElement(".wb-pq-added-power-query");
        Assert.Equal("Power Query added to the workbook", view.Find(".wb-console-head strong").TextContent);
        Assert.Contains(Added, view.Find(".wb-pq-added-power-query").TextContent, StringComparison.Ordinal);
        Assert.Equal([Added], said);
        Assert.Empty(view.FindAll(".wb-pq-add-power-query"));
        var sent = JsonDocument.Parse(_server.Asked.Last(a => a.Route == "POST /scripts/pq/workbook/save").Body).RootElement;
        Assert.True(sent.GetProperty("add").GetBoolean());
        Assert.False(sent.GetProperty("force").GetBoolean());
    }

    [Fact]
    public void A_plain_power_query_file_has_no_workbook_line_and_asks_nothing()
    {
        var view = Render<PowerQueryFileView>(p => p.Add(v => v.Text, "let a = 1 in a").Add(v => v.Path, "/made/up/plain.pq"));
        Assert.Empty(view.FindAll(".wb-pq-workbook"));
        Assert.Null(view.Instance.Workbook);
        Assert.DoesNotContain(_server.Asked, a => a.Route == "POST /scripts/pq/workbook");
    }

    [Fact]
    public void The_new_file_dialog_starts_with_the_workbook_a_tables_tab_asked_for()
    {
        Assert.Equal("scripts?new=powerquery_workbook&from=%2Fmade%2Fup%2FSales%20Report.xlsx", GridsPage.WorkbookQueriesAddress("/made/up/Sales Report.xlsx"));
        var type = new NewFileType("powerquery_workbook", "Edit workbook queries…", ".pq", [".pq"], "scripts", "scripts", "powerquery", "powerquery",
            "An Excel workbook's own Power Query as one linked file.", "workbook queries", ["name", "folder", "source"]);
        _server.Answer("POST /scripts/files/new", """{"path": "/made/up/shop/scripts/Sales Report.pq", "relative": "scripts/Sales Report.pq", "type": "powerquery_workbook", "kind": "powerquery", "page": "scripts", "made": false}""");
        var dialog = Render<NewFileDialog>(p => p.Add(d => d.Type, type).Add(d => d.HasProject, true).Add(d => d.Source, "/made/up/Sales Report.xlsx"));
        Assert.Equal("/made/up/Sales Report.xlsx", dialog.Find("input.new-file-source").GetAttribute("value"));
        Assert.Equal("Sales Report.pq", dialog.Find("input.new-file-name").GetAttribute("value"));
    }
}
