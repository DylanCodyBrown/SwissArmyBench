namespace SwissArmyBench.Web.Api.App;

/// <summary>GET and PUT /app/frontend: the front end the app opens (classic or blazor) and its home page.</summary>
public sealed record FrontendAnswer(string Frontend, string Home);
