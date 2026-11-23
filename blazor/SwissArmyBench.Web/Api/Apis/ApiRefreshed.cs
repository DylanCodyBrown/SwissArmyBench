namespace SwissArmyBench.Web.Api.Apis;

/// <summary>POST /apis/{name}/refresh: the diff.</summary>
public sealed record ApiRefreshed(ApiDiff Diff);
