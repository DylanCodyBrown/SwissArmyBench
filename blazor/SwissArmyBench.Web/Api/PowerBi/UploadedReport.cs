namespace SwissArmyBench.Web.Api.PowerBi;

/// <summary>A dropped report kept on the server for the plan (its upload id and name).</summary>
public sealed record UploadedReport
{
    public string Upload { get; init; } = string.Empty;

    public string File { get; init; } = string.Empty;
}
