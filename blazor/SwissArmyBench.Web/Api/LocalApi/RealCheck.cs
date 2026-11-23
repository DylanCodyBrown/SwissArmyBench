namespace SwissArmyBench.Web.Api.LocalApi;

/// <summary>Will this work for real?: one endpoint's SQL against its connection: the state and its words.</summary>
public sealed record RealCheck(string Endpoint, string Connection, string State, string Words, int Line);
