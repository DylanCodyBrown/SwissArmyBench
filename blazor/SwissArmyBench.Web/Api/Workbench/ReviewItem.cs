namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>One review comment as it is sent (POST /agent/inbox/review): its lines, the code selected there, what
/// was said, the notebook cell it is in (else empty) and whose it is ("user", or "agent" for the agent's note).</summary>
public sealed record ReviewItem(int Line, int End, string Code, string Comment, string Part, string By);
