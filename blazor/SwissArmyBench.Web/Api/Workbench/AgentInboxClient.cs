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
}
