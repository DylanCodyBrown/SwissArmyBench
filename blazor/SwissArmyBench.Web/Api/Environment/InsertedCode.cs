namespace SwissArmyBench.Web.Api.Environment;

/// <summary>POST /environment/insert: a row as code (Python, SQL, or text).</summary>
public sealed record InsertedCode(string? Python = null, string? Sql = null, string? Text = null);
