using SwissArmyBench.Web.Pages.Apis;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>Add API's endpoint card: a path's {word} always needed, a typed star ticks a parameter, Try it's reason,
/// and the card as the form sends it.</summary>
public sealed class AddApiTests
{
    [Fact]
    public void APathsWordIsAlwaysNeededAndBlocksTryIt()
    {
        var card = new EndpointCard { Path = "/orders/{order_id}", Parameters = "status, limit*" };

        Assert.Equal(["order_id", "status", "limit"], card.AllParameters);
        Assert.True(card.IsNeeded("order_id"));
        Assert.True(card.IsNeeded("limit"));
        Assert.False(card.IsNeeded("status"));
        Assert.Equal("It needs a value for a parameter", card.TryReason);
    }

    [Fact]
    public void TryItsReasonFollowsTheCard()
    {
        Assert.Equal("Give it a path", new EndpointCard().TryReason);
        Assert.Equal("Only a GET is tried", new EndpointCard { Method = "POST", Path = "/orders" }.TryReason);
        Assert.Equal("Tick Read as a table to try it", new EndpointCard { Path = "/orders", Table = false }.TryReason);
        Assert.Equal(string.Empty, new EndpointCard { Path = "/orders" }.TryReason);
    }

    [Fact]
    public void TheCardIsSentWithItsNeededParametersStarred()
    {
        var card = new EndpointCard { Path = " /orders ", Parameters = "status, region", Columns = "id, total" };
        card.Needed.Add("region");

        var sent = card.Sent();

        Assert.Equal("/orders", sent["path"]);
        Assert.Equal("status, region*", sent["parameters"]);
        Assert.Equal("id, total", sent["columns"]);
        Assert.Equal(true, sent["table"]);
    }
}
