namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>Send to the agent (routes_agent.py POST /agent/inbox): what the user hands their agent, with a question;
/// memory only, read by the prompt hook and the agent_inbox tool.</summary>
public sealed class AgentInboxClient
{
    private readonly ApiClient _api;

    public AgentInboxClient(ApiClient api)
    {
        _api = api;
    }

    public Task SendAsync(string kind, string title, string text, string note) =>
        _api.PostAsync("/agent/inbox", new { kind, title, text, note });

    /// <summary>Every review comment on one document as ONE message for the agent (the server shapes it, masks a
    /// known secret's value and caps it: domain/review_comments.py). The user's own send.</summary>
    public Task<ReviewSent> ReviewAsync(string path, IReadOnlyList<ReviewItem> comments) =>
        _api.PostAsync<ReviewSent>("/agent/inbox/review", new { path, comments });
}
