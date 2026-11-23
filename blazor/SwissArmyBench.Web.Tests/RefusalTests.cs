using System.Net;

using SwissArmyBench.Web.Api;

using Xunit;

namespace SwissArmyBench.Web.Tests;

public sealed class RefusalTests
{
    [Fact]
    public void TheServersRefusalShapeIsRead()
    {
        var refusal = ApiClient.ReadRefusal(
            """{"error": "No such table.", "where": "orders", "fixes": [{"label": "Try again", "action": "try_again"}], "details": "made up"}""",
            HttpStatusCode.NotFound);

        Assert.Equal("No such table.", refusal.Error);
        Assert.Equal("orders", refusal.Where);
        Assert.Equal("try_again", Assert.Single(refusal.Fixes!).Action);
        Assert.Equal("made up", refusal.Details);
    }

    [Fact]
    public void PlainTextIsTheWords()
    {
        Assert.Equal("Only the Workbench window answers.", ApiClient.ReadRefusal("Only the Workbench window answers.", HttpStatusCode.Forbidden).Error);
        Assert.Equal("The server refused (500).", ApiClient.ReadRefusal(string.Empty, HttpStatusCode.InternalServerError).Error);
    }
}
