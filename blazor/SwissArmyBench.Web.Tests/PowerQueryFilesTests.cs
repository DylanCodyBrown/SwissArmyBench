using System.Text.Json;

using Bunit;

using Microsoft.Extensions.DependencyInjection;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Pages.Grids.Query;
using SwissArmyBench.Web.Pages.Workbench;
using SwissArmyBench.Web.Pages.Workbench.Ide;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>Power Query files on the Scripts page (the owner, 2026-11-27: "Wish I had it as a supported language" /
/// "I just want a run button and the power query runs"): the file's kind of document, its bar, a run's tables in its
/// Output, a failure with its line and Add connection, Show as SQL, the New file dialog's source ask (Import Power BI
/// queries…) and the Tables page's read-only query with Show as SQL.</summary>
public sealed class PowerQueryFilesTests : AppTestContext
{
    private readonly CannedServer _server = new();

    public PowerQueryFilesTests()
    {
        Services.AddScoped(_ => new HttpClient(_server) { BaseAddress = new Uri("http://127.0.0.1:9/") });
        Services.AddScoped<ApiClient>();
        Services.AddScoped<ScriptIdeClient>();
    }

    [Theory]
    [InlineData("/made/up/scripts/shop.pq", true)]
    [InlineData("C:\\made\\up\\Shop.PQ", true)]
    [InlineData("/made/up/queries/shop.m", true)]
    [InlineData("/made/up/shop.sql", false)]
    [InlineData("/made/up/shop.md", false)]
    public void A_power_query_file_is_its_own_kind_of_document(string path, bool isOne)
    {
        var doc = new OpenDocument(1, false) { Path = path };
        Assert.Equal(isOne, doc.IsPowerQuery);
        Assert.Equal(isOne, PowerQueryFileView.IsFile(path));
        if (isOne)
        {
            Assert.False(doc.IsCode); // no Python session: its run is its tables
            Assert.False(doc.IsSql);
            Assert.True(doc.IsQueryFile);
            Assert.True(doc.CanRename);
            Assert.Equal("Power Query file", doc.KindLabel);
        }
    }

    [Fact]
    public void Its_bar_runs_the_file_one_query_and_shows_the_sql()
    {
        var asked = new List<string>();
        var bar = Render<PowerQueryFileBar>(p => p
            .Add(b => b.OnRunFile, () => asked.Add("file"))
            .Add(b => b.OnRunQuery, () => asked.Add("query"))
            .Add(b => b.OnShowSql, () => asked.Add("sql")));
        Assert.Contains("F5", bar.Find(".wb-run-file").GetAttribute("title"), StringComparison.Ordinal);
        Assert.Contains("Ctrl+Enter", bar.Find(".wb-run-selection").GetAttribute("title"), StringComparison.Ordinal);
        bar.Find(".wb-run-file").Click();
        bar.Find(".wb-run-selection").Click();
        bar.Find(".wb-pq-as-sql").Click();
        Assert.Equal(["file", "query", "sql"], asked);

        var running = Render<PowerQueryFileBar>(p => p.Add(b => b.Running, true));
        Assert.All(running.FindAll("button"), b => Assert.True(b.HasAttribute("disabled")));
    }

    [Fact]
    public async Task A_run_lists_each_table_it_built_and_hands_them_overAsync()
    {
        _server.Answer("POST /scripts/pq/run", """
            {"tables": [{"table": "People", "query": "People", "grid": "g1", "rows": 2, "line": 3, "end_line": 3},
                        {"table": "Totals", "query": "Totals", "grid": "g2", "rows": 1, "line": 5, "end_line": 9}],
             "grid": "g2", "table": "Totals", "rows": 1}
            """);
        PowerQueryRun? built = null;
        PowerQueryTable? opened = null;
        var view = Render<PowerQueryFileView>(p => p
            .Add(v => v.Text, "section S;\nshared People = 1;")
            .Add(v => v.Path, "/made/up/shop.pq")
            .Add(v => v.OnBuilt, r => built = r)
            .Add(v => v.OnOpenTable, t => opened = t));
        Assert.True(view.Find(".wb-pq-output").HasAttribute("hidden")); // nothing ran yet

        await view.InvokeAsync(view.Instance.RunFileAsync);
        view.WaitForAssertion(() => Assert.Equal(2, view.FindAll(".wb-pq-table").Count));
        Assert.Equal("Totals", built?.Table);
        Assert.Contains("2 tables built from their original sources.", view.Find(".sql-status").TextContent, StringComparison.Ordinal);
        Assert.Contains("People", view.FindAll(".wb-pq-table")[0].TextContent, StringComparison.Ordinal);
        Assert.Contains("2 rows", view.FindAll(".wb-pq-table")[0].TextContent, StringComparison.Ordinal);
        view.FindAll(".wb-pq-table .wb-sql-open")[0].Click();
        Assert.Equal("g1", opened?.Grid);

        var sent = JsonDocument.Parse(_server.Asked.Last(a => a.Route == "POST /scripts/pq/run").Body).RootElement;
        Assert.Equal("/made/up/shop.pq", sent.GetProperty("path").GetString());
        Assert.False(sent.TryGetProperty("line", out var line) && line.ValueKind != JsonValueKind.Null); // Run file: every table
    }

    [Fact]
    public async Task A_failure_says_its_line_and_offers_add_connectionAsync()
    {
        _server.Refuse("POST /scripts/pq/run", """
            {"error": "No saved connection matches Sql.Database for srv and db: Add connection (a SQL Server one for that server and database).",
             "where": "line 4", "line": 4, "column": 12, "query": "Orders", "add_connection": true}
            """);
        var view = Render<PowerQueryFileView>(p => p.Add(v => v.Text, "section S;").Add(v => v.Path, "/made/up/shop.pq"));
        await view.InvokeAsync(view.Instance.RunFileAsync);
        view.WaitForElement(".wb-sql-error");
        Assert.StartsWith("Line 4: No saved connection matches", view.Find(".wb-sql-error strong").TextContent, StringComparison.Ordinal);
        Assert.Equal("connections?add=1", view.Find(".wb-pq-add-connection").GetAttribute("href"));
        Assert.Contains("Go to line 4", view.Find(".wb-sql-goto").TextContent, StringComparison.Ordinal);
        Assert.Empty(view.FindAll(".wb-pq-table"));
    }

    [Fact]
    public async Task Show_as_sql_shows_what_runs_and_the_sources_it_readsAsync()
    {
        _server.Answer("POST /scripts/pq/sql", """
            {"queries": [{"query": "Big Orders", "table": "Big_Orders", "sql": "SELECT * FROM \"m_source_0\" WHERE ((\"amount\" > 100))", "line": 2,
                          "sources": [{"name": "m_source_0", "function": "Csv.Document", "kind": "file", "words": "/made/up/orders.csv"}]}]}
            """);
        var view = Render<PowerQueryFileView>(p => p.Add(v => v.Text, "let a = 1 in a").Add(v => v.Path, "/made/up/big orders.pq"));
        await view.InvokeAsync(view.Instance.ShowSqlAsync);
        view.WaitForElement(".wb-pq-sql-query");
        Assert.Equal("As SQL", view.Find(".wb-console-head strong").TextContent);
        Assert.Contains("WHERE ((\"amount\" > 100))", view.Find(".wb-pq-sql-query pre").TextContent, StringComparison.Ordinal);
        Assert.Contains("m_source_0: /made/up/orders.csv", view.Find(".wb-pq-sql-query .muted").TextContent, StringComparison.Ordinal);
    }

    [Fact]
    public void The_new_file_dialog_asks_the_file_an_import_is_made_from()
    {
        var import = new NewFileType("powerquery_import", "Import Power BI queries…", ".pq", [".pq"], "scripts", "scripts", "powerquery", "powerquery",
            "Every query of a Power BI dataset as one file.", "dataset", ["name", "folder", "source"]);
        _server.Answer("POST /scripts/files/new", """{"path": "/made/up/shop/scripts/dataset.pq", "relative": "scripts/dataset.pq", "type": "powerquery_import", "kind": "powerquery", "page": "scripts", "made": false}""");
        var dialog = Render<NewFileDialog>(p => p.Add(d => d.Type, import).Add(d => d.HasProject, true));
        Assert.Equal("dataset.pq", dialog.Find("input.new-file-name").GetAttribute("value"));
        Assert.Equal("From the file", dialog.Find("label.field:has(input.new-file-source) > span").TextContent);
        Assert.Contains("Browse", dialog.Find(".new-file-source-browse").TextContent, StringComparison.Ordinal);

        dialog.Find("input.new-file-source").Input("/made/up/Sales.pbit");
        dialog.Find(".new-file-create").Click();
        dialog.WaitForAssertion(() =>
        {
            var sent = JsonDocument.Parse(_server.Asked.Last(a => a.Route == "POST /scripts/files/new").Body).RootElement;
            Assert.Equal("/made/up/Sales.pbit", sent.GetProperty("source").GetString());
            Assert.Equal("powerquery_import", sent.GetProperty("type").GetString());
        });

        // A type that asks no source has no such box.
        var plain = new NewFileType("powerquery", "Power Query", ".pq", [".pq", ".m"], "scripts", "scripts", "powerquery", "powerquery", "A let ... in query.", "query");
        Assert.Empty(Render<NewFileDialog>(p => p.Add(d => d.Type, plain).Add(d => d.HasProject, true)).FindAll("input.new-file-source"));
    }

    [Fact]
    public void A_power_querys_table_shows_its_m_and_the_sql_composed_from_it()
    {
        var shown = Render<QueryShown>(p => p
            .Add(q => q.Sql, "shared Big = Table.SelectRows(orders, each [amount] > 6);")
            .Add(q => q.Table, "Big")
            .Add(q => q.Language, "powerquery")
            .Add(q => q.ComposedSql, "SELECT * FROM \"orders\" WHERE ((\"amount\" > 6))"));
        Assert.Equal("Power Query", shown.Find(".query-shown-bar strong").TextContent);
        Assert.Equal("from its original sources", shown.Find(".query-shown-on").TextContent);
        Assert.Contains("Table.SelectRows", shown.Find(".query-shown-sql").TextContent, StringComparison.Ordinal);
        Assert.Equal("Power Query (M)", shown.Find(".query-shown-sql").GetAttribute("aria-label"));

        shown.Find(".query-as-sql").Click();
        Assert.Contains("SELECT * FROM \"orders\"", shown.Find(".query-shown-sql").TextContent, StringComparison.Ordinal);
        Assert.Contains("Show the query", shown.Find(".query-as-sql").TextContent, StringComparison.Ordinal);

        // A SQL query's table is as it was: no Show as SQL.
        var sql = Render<QueryShown>(p => p.Add(q => q.Sql, "SELECT 1").Add(q => q.Table, "one"));
        Assert.Equal("Query", sql.Find(".query-shown-bar strong").TextContent);
        Assert.Empty(sql.FindAll(".query-as-sql"));
    }
}
