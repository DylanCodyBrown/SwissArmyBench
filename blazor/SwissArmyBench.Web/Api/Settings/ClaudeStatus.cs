namespace SwissArmyBench.Web.Api.Settings;

/// <summary>GET /claude: Claude Code and Claude Desktop as found here, and the bypass switch.</summary>
public sealed record ClaudeStatus(bool Bypass, ClaudeKind Code, ClaudeKind Desktop);
