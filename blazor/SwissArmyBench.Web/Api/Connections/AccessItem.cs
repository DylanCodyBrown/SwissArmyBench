namespace SwissArmyBench.Web.Api.Connections;

/// <summary>One thing an app registration reaches or is refused (never a token or a row).</summary>
public sealed record AccessItem(
    string Target,
    bool? Ok = null,
    string Mark = "",
    string Reason = "",
    string Fix = "");
