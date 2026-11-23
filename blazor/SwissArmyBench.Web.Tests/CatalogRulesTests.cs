using System.Text.Json;

using SwissArmyBench.Web.Api.Catalog;
using SwissArmyBench.Web.Pages.Catalog;
using SwissArmyBench.Web.Pages.Home;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>The Catalog tree's rules (a browse answer as its nodes, a connection's state in words, a column's
/// nulls) and a project folder's name in the classic questions.</summary>
public sealed class CatalogRulesTests
{
    private static BrowseConnection Connection(string name, IReadOnlyList<BrowseGroup> groups, bool loaded = true, string state = "loaded", bool password = false) =>
        new(name, "duckdb", "database", new BrowseState(state), loaded, groups.Sum(g => g.Count), Relationships: false, password, groups);

    private static SearchResult Table(string name) =>
        new($"tables/MadeUpBooks/{name}", "tables", name, ["MadeUpBooks"], "MadeUpBooks", Place: new TablePlace(name)) { Source = "catalog" };

    [Fact]
    public void OneUnnamedGroupsTablesSitStraightUnderTheirConnection()
    {
        var answer = new BrowseAnswer([Connection("MadeUpBooks", [new BrowseGroup(string.Empty, string.Empty, 1, [Table("ledger")])])], []);

        var root = Assert.Single(CatalogTreeNodes.Of(answer));

        Assert.Equal("connection", root.Kind);
        Assert.True(root.OpenAtFirst);
        var table = Assert.Single(root.Children!);
        Assert.Equal("table", table.Kind);
        Assert.True(table.Lazy);
        Assert.Empty(table.Children!);
    }

    [Fact]
    public void SchemasAreGroupsAndSectionsFollowTheConnections()
    {
        var answer = new BrowseAnswer(
            [Connection("MadeUpBooks", [new BrowseGroup("shop", "main", 1, [Table("ledger")]), new BrowseGroup("shop", "archive", 1, [Table("old")])])],
            [new BrowseSection("open", "Open tables", 1, [new SearchResult("tables//Open tables/orders", "tables", "orders", ["Open tables"]) { Source = "grid" }])]);

        var nodes = CatalogTreeNodes.Of(answer);

        Assert.Equal(["MadeUpBooks", "Open tables"], nodes.Select(n => n.Label));
        Assert.Equal(["main", "archive"], nodes[0].Children!.Select(g => g.Label));
        Assert.Equal("section", nodes[1].Kind);
        Assert.Null(nodes[1].Children![0].Children);
    }

    [Theory]
    [InlineData(true, "loaded", false, "Needs a password")]
    [InlineData(false, "loading", false, "Loading its tables…")]
    [InlineData(false, "failed", false, "Its tables did not load")]
    [InlineData(false, "none", false, "Not loaded")]
    [InlineData(true, "loaded", true, "1 table")]
    public void AConnectionsStateIsSaidInWords(bool loaded, string state, bool counted, string words)
    {
        var c = Connection("MadeUpBooks", counted ? [new BrowseGroup(string.Empty, string.Empty, 1, [])] : [], loaded, state, password: words == "Needs a password");

        Assert.Equal(words, CatalogTreeNodes.StateWords(c));
    }

    [Theory]
    [InlineData("\"YES\"", "Yes")]
    [InlineData("\"NO\"", "No")]
    [InlineData("true", "Yes")]
    [InlineData("false", "No")]
    [InlineData("1", "Yes")]
    [InlineData("\"\"", "")]
    [InlineData("null", "")]
    public void AColumnsNullsAreYesNoOrNothing(string json, string words) =>
        Assert.Equal(words, new DetailColumn("amount", "DOUBLE", JsonDocument.Parse(json).RootElement).NullsWords);

    [Theory]
    [InlineData("/made/up/shop", "shop")]
    [InlineData("C:\\made\\up\\shop\\", "shop")]
    public void AFoldersNameIsItsLastPart(string path, string name) => Assert.Equal(name, ProjectAsks.BaseName(path));
}
