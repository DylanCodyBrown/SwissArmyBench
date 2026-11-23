using Bunit;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Catalog;
using SwissArmyBench.Web.Api.Projects;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.Layout;
using SwissArmyBench.Web.Layout.Tour;
using SwissArmyBench.Web.Pages.Catalog;
using SwissArmyBench.Web.State;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>The app-wide parts: the missing-package prompt and its reminder, the error note's older fixes, the
/// picker's breadcrumb, a typed search's narrowed tree, the tour's made-up tables and a shared card's sync words.</summary>
public sealed class AppWideTests : AppTestContext
{
    private static readonly MissingPackages _excel = new("Excel files", ["openpyxl"], MissingPackages.AppPython, "pip install openpyxl");

    [Fact]
    public void TheMissingPackagesAreReadFromARefusal()
    {
        const string body = """{"error": "Excel files need openpyxl.", "missing": {"feature": "Excel files", "packages": ["openpyxl", "xlrd"], "python": "app", "command": "pip install openpyxl xlrd"}}""";

        var missing = MissingPackages.Of(new ApiException(422, new Refusal("Excel files need openpyxl."), body));

        Assert.NotNull(missing);
        Assert.Equal("openpyxl and xlrd", missing.Listed);
        Assert.Null(MissingPackages.Of("""{"error": "No."}"""));
    }

    [Fact]
    public async Task ThePromptSaysTheFeatureAndNotNowHoldsForTheSessionAsync()
    {
        var host = Render<PackagePromptHost>();
        var prompts = Get<PackagePrompts>();

        var asked = prompts.PromptAsync(_excel);
        host.Render();

        Assert.Equal("Install openpyxl?", host.Find(".dialog-head h2").TextContent);
        Assert.Contains("Excel files will not work without openpyxl.", host.Find(".missing-sentence").TextContent);
        host.FindAll(".dialog-foot button").Single(b => b.TextContent.Contains("Not now")).Click();

        Assert.False(await asked);
        Assert.True(prompts.Dismissed(_excel));
        Assert.False(await prompts.PromptAsync(_excel));
    }

    [Fact]
    public void TheReminderOpensThePromptAgain()
    {
        var host = Render<PackagePromptHost>();
        Get<PackagePrompts>().Answer(false);
        var reminder = Render<InstallReminder>(p => p.Add(x => x.Missing, _excel));

        Assert.Equal("pip install openpyxl", reminder.Find("button").GetAttribute("title"));
        reminder.Find("button").Click();
        host.Render();

        Assert.Equal("Install openpyxl?", host.Find(".dialog-head h2").TextContent);
    }

    [Fact]
    public void AnOlderAnswerGetsInstallNowAndSetIt()
    {
        const string body = """{"error": "Two things are missing.", "missing": {"feature": "Excel files", "packages": ["openpyxl"], "python": "app", "command": "pip install openpyxl"}, "missing_variables": ["MADE_UP_HOST"]}""";
        var note = Render<ErrorNote>(p => p.Add(x => x.Error, new ApiException(422, ApiClient.ReadRefusal(body, System.Net.HttpStatusCode.UnprocessableEntity), body)));

        var fixes = note.FindAll(".error-note-fixes button").Select(b => b.TextContent).ToList();

        Assert.Contains("Install now", fixes);
        Assert.Contains("Set it", fixes);
    }

    [Fact]
    public void SetItOpensAddVariableWithTheName()
    {
        var host = Render<VariableAskHost>();

        _ = Get<VariableAsks>().AddAsync("MADE_UP_PASSWORD");
        host.Render();

        Assert.Equal("MADE_UP_PASSWORD", host.Find("input[aria-label=Name]").GetAttribute("value"));
        // A name that reads as a secret starts in the keyring.
        Assert.Equal("password", host.Find("input[aria-label=Value]").GetAttribute("type"));
    }

    [Theory]
    [InlineData("/home/made_up/data", "/", "/|home|made_up|data", "/home/made_up/data")]
    [InlineData(@"C:\Users\made_up", "\\", @"C:\|Users|made_up", @"C:\Users\made_up")]
    [InlineData("/", "/", "/", "/")]
    public void TheBreadcrumbsParts(string path, string separator, string names, string last)
    {
        var crumbs = FolderCrumb.Of(path, separator);

        Assert.Equal(names, string.Join('|', crumbs.Select(c => c.Name)));
        Assert.Equal(last, crumbs[^1].Path);
    }

    [Fact]
    public void ATypedSearchIsTheTreeNarrowed()
    {
        var place = new TablePlace("orders", "shop", "main");
        SearchResult column = new("columns/Shop/orders/customer_id", "columns", "customer_id", ["Shop", "orders"], "Shop", Place: place) { Source = "catalog", Type = "INTEGER" };
        SearchResult open = new("tables/grid/g1", "tables", "customers", [], Grid: "g1") { Source = "grid" };
        var answer = new SearchAnswer([new SearchGroup("tables", "Tables", 1, [open]), new SearchGroup("columns", "Columns", 1, [column])]);

        var tree = CatalogSearchTree.Of(answer, null);

        var shop = Assert.Single(tree.Connections);
        Assert.Equal("Shop", shop.Name);
        var table = Assert.Single(Assert.Single(shop.Groups).Tables);
        Assert.Equal("orders", table.Name);
        Assert.Equal("customer_id", Assert.Single(table.Children!).Name);
        Assert.Equal("Open tables", Assert.Single(tree.Sections).Label);
    }

    [Fact]
    public void TheToursTablesAreMadeUpAndNamedApart()
    {
        var taken = new HashSet<string> { "tour_orders" };

        Assert.Equal("tour_orders_2", TourTables.FreeName("tour_orders", taken));
        Assert.StartsWith("customer_id\tname\tcity\n1\tAda Fernwood\tNorthvale\n", TourTables.CustomersText());
        Assert.Equal(13, TourTables.OrdersText().Trim().Split('\n').Length);
    }

    [Theory]
    [InlineData(0, 0, true, 0, null)]
    [InlineData(2, 0, true, 0, "↑2 to push")]
    [InlineData(0, 1, true, 3, "Conflicts: 1")]
    [InlineData(0, 0, true, 3, "↓3 behind")]
    [InlineData(0, 0, false, 0, "↓ Pull")]
    public void ASharedCardsSyncWords(int toPush, int conflicts, bool pulled, int behind, string? words)
    {
        var folder = new SyncFolder("shared", true, pulled, behind, new Dictionary<string, ProjectSync> { ["made_up"] = new(toPush, conflicts) });

        Assert.Equal(words, folder.WordsFor("made_up"));
        Assert.Null((folder with { Connected = false }).WordsFor("made_up"));
    }

    [Fact]
    public void LeaveANoteEndsEveryMenuWhileBetaModeIsOn()
    {
        var beta = Get<BetaState>();
        typeof(BetaState).GetProperty(nameof(BetaState.On))!.SetValue(beta, true);
        var menu = Render<ContextMenu>(p => p
            .Add(x => x.Title, "Orders")
            .Add(x => x.Entries, [new MenuEntry("Rename", "edit", () => Task.CompletedTask)]));

        menu.FindAll("[role=menuitem]").Last().Click();

        Assert.Equal("Menu: Orders", beta.Noting);
    }
}
