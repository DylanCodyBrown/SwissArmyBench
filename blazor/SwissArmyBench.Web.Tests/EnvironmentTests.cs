using SwissArmyBench.Web.Pages.Environment;
using SwissArmyBench.Web.Pages.Structures;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>The Environment's and the Structures page's own rules: a search's words marked as the server matched
/// them, a node's way as the app writes it.</summary>
public sealed class EnvironmentTests
{
    [Fact]
    public void TheSearchMarksTheShortestStretchThatSpellsAWord()
    {
        Assert.Equal([("customer_id", false)], TextMarks.Of("customer_id", string.Empty));
        Assert.Equal([("cust", true), ("omer_id", false)], TextMarks.Of("customer_id", "cust"));
        Assert.Equal([("Cust", true), ("omerKey", false)], TextMarks.Of("CustomerKey", "CUST"));
        Assert.Equal([("customer_id", true)], TextMarks.Of("customer_id", "customerid"));
    }

    [Fact]
    public void ANodesWayIsWrittenAsTheAppWritesIt()
    {
        Assert.Equal("$", StructureTree.PathText([]));
        Assert.Equal("$.orders[3].total", StructureTree.PathText(["orders", 3, "total"]));
        Assert.Equal("$[\"order date\"]", StructureTree.PathText(["order date"]));
    }
}
