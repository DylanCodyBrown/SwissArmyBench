namespace SwissArmyBench.Web.Api.Sharing;

/// <summary>A device code's sign-in: the page to open and the code to type there.</summary>
public sealed record DeviceCode
{
    public string Url { get; init; } = string.Empty;

    public string Code { get; init; } = string.Empty;
}
