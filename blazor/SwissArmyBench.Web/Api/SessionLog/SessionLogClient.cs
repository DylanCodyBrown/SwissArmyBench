namespace SwissArmyBench.Web.Api.SessionLog;

/// <summary>The Session page's log (routes_session_log.py).</summary>
public sealed class SessionLogClient
{
    private const int MostEntries = 1000;

    private readonly ApiClient _api;

    public SessionLogClient(ApiClient api)
    {
        _api = api;
    }

    /// <param name="who">agent, user or both.</param>
    /// <param name="changesOnly">Only the entries that changed something (Changes).</param>
    public Task<SessionLogAnswer> ListingAsync(string who, bool changesOnly) =>
        _api.GetAsync<SessionLogAnswer>($"/session-log?who={who}&limit={MostEntries}{(changesOnly ? "&changes=1" : string.Empty)}");

    /// <summary>Follow the agent on or off (the user's switch).</summary>
    public Task<FollowAnswer> SetFollowAsync(bool on) => _api.PutAsync<FollowAnswer>("/session-log/follow", new { on });
}
