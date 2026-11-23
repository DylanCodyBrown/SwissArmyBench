namespace SwissArmyBench.Web.Api;

/// <summary>A refusal from the server, or a request that never reached it (status 0).</summary>
public sealed class ApiException : Exception
{
    public ApiException(int status, Refusal refusal, string body)
        : base(refusal.Error)
    {
        Status = status;
        Refusal = refusal;
        Body = body;
    }

    public int Status { get; }

    public Refusal Refusal { get; }

    /// <summary>The answer's text as it came (some refusals carry more than the shape: missing, needs).</summary>
    public string Body { get; }
}
